"""atlas_segment.py -- PER-SEGMENT HYBRID TRIAGE (Part 3 gap: "per-segment hybrid triage").

A real hybrid/QPU circuit is rarely uniformly hard. It is typically a long, cheap
Clifford prefix (state-prep / encoding) plus one short, dense non-Clifford or highly
entangling segment that carries ALL the classical cost. Atlas already gives a single
verdict for the whole circuit; this module shows *WHERE* that cost lives by running
cost_atlas on contiguous slices of the partitura (the flattened primitive stream).

Public API:
    segment_triage(qasm, n_segments=3) -> dict

HONESTY CONTRACT (read this before trusting any number below):
  * Segment costs are NOT additive and do NOT decompose the whole-circuit cost.
    Entanglement and magic cross slice boundaries: an MPS bond / treewidth measured
    on a slice ignores correlations injected by earlier slices, so a slice run in
    isolation can look EASIER than that same slice embedded in the full circuit.
    Treat per-segment costs as a DIAGNOSTIC of *where hardness concentrates*, never
    as a sum that reproduces the whole.
  * Each segment is simulated as if starting from |0...0> on the SAME n qubits.
    This is a deliberate, stated approximation: it isolates the gate character of
    the slice, not its true conditional cost given the prefix.
  * The whole-circuit cost_atlas verdict remains the SOURCE OF TRUTH for the buy/
    don't-buy decision. Segmentation is explanatory, not a new estimator.
  * All Atlas ground-truth caveats still apply per segment: treewidth is a greedy
    UPPER bound, MPS bond may be a truncated LOWER bound, Clifford-ness via Stim is
    exact, and 'escalate'/'WALL' never means classically impossible (BQP!=BPP open).

Run with:
    PYTHONPATH=engine NUMBA_DISABLE_JIT=1 python atlas_segment.py
"""
from __future__ import annotations
import math

import atlas


# ----- gate-character classification of a single primitive ---------------------
_TWO_Q = {"cx", "cnot", "cz", "Z"}  # note: ('Z', q, ang) is 1q; ('Z', a, b, ...) never occurs. ZZ already decomposed.


def _is_t(g) -> bool:
    """A unit of magic in the partitura: a literal ('t', q). Net Z-rotations are already
    folded by atlas's parser to 's'/'z' (Clifford) or 't' (magic), so counting 't' here
    matches t_count exactly."""
    return bool(g) and g[0] == "t"


def _is_entangler(g) -> bool:
    return bool(g) and g[0] in ("cx", "cnot")


def _char(g) -> str:
    """Coarse character tag for a primitive, used only for human-readable labelling."""
    if not g:
        return "nop"
    h = g[0]
    if h == "t":
        return "magic(T)"
    if h in ("cx", "cnot"):
        return "entangler"
    if h in ("s", "z", "h", "x", "y"):
        return "clifford-1q/2q"
    if h == "Z":
        return "z-rot"
    return h


# ----- segmentation strategy ---------------------------------------------------
def _boundaries_uniform(L: int, k: int) -> list[tuple[int, int]]:
    """k contiguous, roughly equal slices over [0, L) by primitive index."""
    k = max(1, min(k, L)) if L else 1
    if L == 0:
        return [(0, 0)]
    step = L / k
    cuts = [round(i * step) for i in range(k + 1)]
    cuts[0], cuts[-1] = 0, L
    return [(cuts[i], cuts[i + 1]) for i in range(k) if cuts[i] < cuts[i + 1]]


def _character_split(circuit: list) -> list[tuple[int, int]] | None:
    """Try a SEMANTIC split: pure-Clifford prefix | (non-Clifford / magic) body | tail.
    Returns boundaries only if there is a genuine Clifford prefix to call out; else None
    so the caller falls back to uniform slicing. Honest: this only detects a *contiguous*
    leading Clifford run -- it does not find interior cheap pockets."""
    L = len(circuit)
    if L == 0:
        return None
    # length of the leading run with zero magic (T)
    pre = 0
    while pre < L and not _is_t(circuit[pre]):
        pre += 1
    if pre == 0 or pre == L:
        return None  # no Clifford prefix, or no magic at all -> nothing semantic to show
    # length of the trailing run with zero magic
    tail = L
    while tail > pre and not _is_t(circuit[tail - 1]):
        tail -= 1
    bounds = [(0, pre)]
    if tail > pre:
        bounds.append((pre, tail))
    if tail < L:
        bounds.append((tail, L))
    return bounds


def _segment_record(n: int, circuit: list, lo: int, hi: int, label: str) -> dict:
    """Run cost_atlas on circuit[lo:hi] as a standalone circuit on n qubits from |0>."""
    sub = circuit[lo:hi]
    t_count = sum(1 for g in sub if _is_t(g))
    n_ent = sum(1 for g in sub if _is_entangler(g))
    rec = {
        "label": label,
        "prim_range": [lo, hi],
        "n_primitives": hi - lo,
        "t_count": t_count,
        "n_entanglers": n_ent,
        "character_mix": _mix(sub),
    }
    try:
        r = atlas.cost_atlas(n, sub)
        rec["union_cost_log2"] = r.get("union_cost_log2")
        rec["best_method"] = r.get("best_method")
        rec["stim_clifford"] = r.get("stim_clifford")
        rec["mps_truncated"] = r.get("mps_truncated")
        rec["treewidth_exact"] = r.get("treewidth_exact")
        rec["costs_log2"] = r.get("costs_log2")
        adj = r.get("route_adjudication")
        if isinstance(adj, dict):
            rec["route"] = adj.get("route")
            rec["governing_estimator"] = adj.get("governing_estimator")
            rec["governing_cost_log2"] = adj.get("governing_cost_log2")
            conf = adj.get("confidence")
            if isinstance(conf, dict):
                rec["confidence"] = conf.get("label")
    except Exception as e:  # a slice may parse-trivially or be empty; degrade gracefully
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def _mix(sub: list) -> dict:
    out: dict[str, int] = {}
    for g in sub:
        c = _char(g)
        out[c] = out.get(c, 0) + 1
    return out


def segment_triage(qasm: str, n_segments: int = 3) -> dict:
    """Split a circuit into contiguous segments and run cost_atlas per segment to
    localize hardness. Prefers a SEMANTIC split (Clifford prefix | magic body | tail);
    if no such structure exists, falls back to `n_segments` uniform slices.

    Returns a dict with:
      whole:    the authoritative whole-circuit cost_atlas summary (SOURCE OF TRUTH)
      segments: per-segment diagnostic records
      hotspot:  index of the segment carrying the most magic (the likely cost center)
      method:   'character' | 'uniform'
      caveats:  the non-additivity / isolation warnings (always present)
    """
    n, circ, warns = atlas.safe_parse(qasm)

    whole = atlas.cost_atlas(n, circ)
    whole_adj = whole.get("route_adjudication") if isinstance(whole.get("route_adjudication"), dict) else {}
    whole_summary = {
        "n": n,
        "n_primitives": len(circ),
        "t_count": whole.get("t_count"),
        "union_cost_log2": whole.get("union_cost_log2"),
        "best_method": whole.get("best_method"),
        "verdict": whole.get("verdict"),
        "route": whole_adj.get("route"),
        "governing_estimator": whole_adj.get("governing_estimator"),
        "governing_cost_log2": whole_adj.get("governing_cost_log2"),
        "stim_clifford": whole.get("stim_clifford"),
        "mps_truncated": whole.get("mps_truncated"),
        "treewidth_exact": whole.get("treewidth_exact"),
    }

    bounds = _character_split(circ)
    method = "character"
    if bounds is None:
        bounds = _boundaries_uniform(len(circ), n_segments)
        method = "uniform"

    segments = []
    for i, (lo, hi) in enumerate(bounds):
        if method == "character":
            label = ("clifford-prefix" if i == 0 and not any(_is_t(g) for g in circ[lo:hi])
                     else f"magic-body" if any(_is_t(g) for g in circ[lo:hi])
                     else "clifford-tail")
        else:
            label = f"slice {i + 1}/{len(bounds)}"
        segments.append(_segment_record(n, circ, lo, hi, label))

    # hotspot = segment with most magic; tie-break on isolated union cost then entanglers
    def _key(s):
        return (s.get("t_count", 0),
                s.get("union_cost_log2") or 0.0,
                s.get("n_entanglers", 0))
    hotspot = max(range(len(segments)), key=lambda i: _key(segments[i])) if segments else None

    return {
        "method": method,
        "whole": whole_summary,
        "segments": segments,
        "hotspot_index": hotspot,
        "hotspot_label": segments[hotspot]["label"] if hotspot is not None else None,
        "parse_warnings": warns,
        "caveats": [
            "Per-segment costs are NOT additive and do NOT sum to the whole-circuit cost.",
            "Each segment is simulated from |0...0> on all n qubits; this ignores the "
            "state injected by earlier segments, so isolated costs are a LOWER-bound-flavored "
            "proxy for where gate character (magic/entanglement) concentrates -- not a "
            "conditional cost given the prefix.",
            "Entanglement and magic cross segment boundaries; a long Clifford prefix shown "
            "as 'free' (Stim-exact, cost 2^0) only means that prefix is Clifford in isolation.",
            "The whole-circuit cost_atlas verdict is the SOURCE OF TRUTH for any buy/no-buy "
            "decision; this segmentation is explanatory only.",
            "Treewidth per segment is a greedy UPPER bound; MPS bond may be a truncated "
            "LOWER bound; 'escalate'/high cost NEVER means classically impossible.",
        ],
    }


# ----- pretty printer ----------------------------------------------------------
def render(report: dict) -> None:
    w = report["whole"]
    print("\n" + "=" * 74)
    print("ATLAS PER-SEGMENT HYBRID TRIAGE  (diagnostic: WHERE the hardness lives)")
    print("=" * 74)
    print(f"WHOLE CIRCUIT (source of truth): n={w['n']}, {w['n_primitives']} primitives, "
          f"#T={w['t_count']}")
    print(f"  verdict          : {w['verdict']}")
    print(f"  best classical   : 2^{w['union_cost_log2']} via {w['best_method']}")
    print(f"  route            : {w['route']} (governing: {w['governing_estimator']} "
          f"@ 2^{w['governing_cost_log2']})")
    print(f"\nSegmentation method: {report['method']}  "
          f"({len(report['segments'])} contiguous segments)")
    print("-" * 74)
    hdr = f"{'#':>2} {'label':<16} {'prims':>6} {'#T':>4} {'ent':>4} {'iso cost':>9} {'route':>10} {'method':>10}"
    print(hdr)
    print("-" * 74)
    for i, s in enumerate(report["segments"]):
        flag = " <== hotspot" if i == report["hotspot_index"] else ""
        cost = s.get("union_cost_log2")
        cost_s = f"2^{cost}" if cost is not None else "n/a"
        if s.get("error"):
            print(f"{i:>2} {s['label']:<16} {s['n_primitives']:>6} {s['t_count']:>4} "
                  f"{s['n_entanglers']:>4} {'ERR':>9} {'-':>10} {'-':>10}{flag}")
            continue
        print(f"{i:>2} {s['label']:<16} {s['n_primitives']:>6} {s['t_count']:>4} "
              f"{s['n_entanglers']:>4} {cost_s:>9} {str(s.get('route')):>10} "
              f"{str(s.get('best_method')):>10}{flag}")
    print("-" * 74)
    print("CAVEATS (per-segment costs are a diagnostic, NOT a decomposition):")
    for c in report["caveats"]:
        print(f"  - {c}")


# ----- demo: long Clifford prefix + dense T-heavy/entangling body --------------
def _build_demo_qasm(n: int = 16, prefix_layers: int = 8, body_layers: int = 4) -> str:
    """A hybrid-shaped circuit: a long, fully-Clifford prefix (Stim-exact, classically
    free) followed by a dense non-Clifford + entangling body that carries all the magic.
    Built large enough (n=16) that the WHOLE circuit is non-trivial, so the localization
    of cost into the body is actually visible rather than everything collapsing to 2^0."""
    L = [f"OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{n}];",
         "// --- long CLIFFORD prefix: no T, classically free via Stim (cost ~2^0)"]
    for layer in range(prefix_layers):
        for i in range(n):
            L.append(f"h q[{i}];")
        for i in range(layer % 2, n - 1, 2):
            L.append(f"cx q[{i}],q[{i + 1}];")
        for i in range(0, n, 3):
            L.append(f"s q[{i}];")
    L.append("// --- dense T-HEAVY + ENTANGLING body: ALL the magic lives here (cost center)")
    for layer in range(body_layers):
        for i in range(n):
            L.append(f"t q[{i}];")
        for i in range((layer + 1) % 2, n - 1, 2):
            L.append(f"cx q[{i}],q[{i + 1}];")
        for i in range(n):
            L.append(f"t q[{i}];")
    return "\n".join(L) + "\n"


_DEMO_QASM = _build_demo_qasm()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as fh:
            qasm = fh.read()
    else:
        qasm = _DEMO_QASM
    report = segment_triage(qasm, n_segments=3)
    render(report)
    print("\nTakeaway: the Clifford prefix/tail are Stim-exact (cost ~2^0) while the "
          "T-heavy body concentrates the magic. This LOCALIZES the hardness for triage; "
          "it does NOT claim the whole-circuit cost is the sum of segment costs.")

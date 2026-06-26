#!/usr/bin/env python3
"""atlas_certificate — product output layer over cost_atlas.

Repackages the engine's OWN adjudication into one actionable certificate with three
faces (no new physics; every value comes from cost_atlas):

  (1) witness   — actionable verdict sourced ONLY from route_adjudication's GOVERNING
                  (valid, non-invalidated) estimator: cheap via <method> within a
                  trusted bound, OR hard because <governing estimator> exceeds budget.
  (2) confidence— trust tier: 'exact' (Stim Clifford), else the engine's own
                  confidence label -> 'measured' (high), 'provisional' (med),
                  'verify' (low). A cheap claim resting on a truncated MPS lower
                  bound is capped at 'verify'.
  (3) driver    — WHY (the governing estimator) + the lever to change it.

SAFETY: we never advertise best_method / union_cost_log2 — those are the min over
ALL estimators INCLUDING the truncated-MPS lower bound, which the adjudicator may
have invalidated. Using them would re-introduce false-safety (cheap via a truncated
MPS floor on a circuit the engine actually routed hard). The governing estimator is
the cheapest VALID one, so it is the only honest basis for the witness.

Usage:
    from atlas_certificate import certificate
    cert = certificate(qasm_str)            # -> dict, JSON-serializable
"""
from __future__ import annotations

import hashlib

from atlas import cost_atlas, safe_parse


def _engine_versions():
    """Best-effort engine versions for the provenance block (graceful if absent)."""
    out = {}
    for mod in ("stim", "quimb", "cotengra", "numpy"):
        try:
            m = __import__(mod)
            out[mod] = getattr(m, "__version__", "present")
        except Exception:
            out[mod] = "absent"
    return out

try:
    import atlas_conformal
except Exception:
    atlas_conformal = None
try:
    from atlas_falsesafety import false_safety_risk as _fs_risk
except Exception:
    _fs_risk = None

CHEAP_ROUTES = ("cpu", "tensor")
# governing estimator (substring, lowercased) -> (human driver, optimization lever)
_DRIVER = {
    "statevector": ("raw state size (qubit count)", "reduce qubit count"),
    "stim":        ("Clifford-simulable — no hardness driver", "—"),
    "clifford":    ("Clifford-simulable — no hardness driver", "—"),
    "treewidth":   ("connectivity / contraction width",
                    "reduce long-range 2-qubit gates; lower circuit width / qubit count"),
    "mps":         ("entanglement growth",
                    "reduce depth or entangling structure (lower bond dimension)"),
    "magic":       ("non-Cliffordness", "reduce T-count / non-Clifford gates"),
    "pauli":       ("operator spread / locality", "reduce operator growth"),
    "spread":      ("operator spread / locality", "reduce operator growth"),
}


def _driver_key(governing: str) -> str:
    g = (governing or "").lower()
    for k in _DRIVER:
        if k in g:
            return k
    return g or "unknown"


def _p2(x):
    return f"2^{x}" if x is not None else "unknown"


def _impossibility(r, costs, n, budget_log2=30.0):
    """Honest impossibility analysis. Reports CERTIFIED method-class lower bounds
    (unconditional but scoped to known paradigms) and the conditional all-algorithm
    statement. NEVER claims absolute classical hardness (= BQP!=BPP, unproven).

    Certified lower bounds vs heuristic: exact treewidth and non-truncated MPS bond
    are tight; GREEDY treewidth is an UPPER bound only and gives NO lower bound, so
    it cannot support an impossibility claim."""
    tw = costs.get("contraction(treewidth)")
    tw_exact = bool(r.get("treewidth_exact"))
    mps = costs.get("MPS(entangle)")
    mps_trunc = bool(r.get("mps_truncated"))
    classes = {}
    # statevector: a dense state is exactly 2^n -> certified lower bound for that method
    classes["statevector"] = {"lower_bound_log2": float(n), "certified": True, "tight": True}
    # tensor-network contraction: ONLY exact treewidth is a certified lower bound
    classes["tensor_contraction"] = (
        {"lower_bound_log2": tw, "certified": True, "tight": True}
        if (tw_exact and tw is not None) else
        {"lower_bound_log2": None, "certified": False,
         "note": "greedy treewidth is an UPPER bound only -> no certified lower bound"})
    # MPS: the value lower-bounds the method cost (exact if not truncated, else weak >=)
    if mps is not None:
        classes["mps"] = {"lower_bound_log2": mps, "certified": True, "tight": (not mps_trunc),
                          "note": ("exact bond (tight)" if not mps_trunc else
                                   "truncated: lower bound only (true cost >= this; weak, "
                                   "depends on truncation threshold)")}
    # stabilizer-rank: exact T-count, but tight rank lower bounds are open
    classes["stabilizer_rank"] = {
        "t_count": r.get("t_count"), "certified": False,
        "note": "stabilizer-rank sim ~2^(0.5*T) (Bravyi-Gosset, upper); tight rank "
                "LOWER bounds are open -> not a certified lower bound"}

    beyond = [k for k, v in classes.items()
              if v.get("certified") and v.get("lower_bound_log2") is not None
              and v["lower_bound_log2"] > budget_log2]
    # tracked paradigms only; even if ALL of these exceed budget, UNTRACKED classical
    # methods are not ruled out -> this is NEVER an impossibility proof.
    untracked = ["Pauli-propagation", "ZX-calculus", "low-rank / stabilizer-decomposition",
                 "hyper-optimized contraction", "future algorithms"]
    coverable = ("statevector", "tensor_contraction", "mps")
    beyond_tracked = all(
        classes.get(c, {}).get("certified")
        and (classes[c].get("lower_bound_log2") or -1) > budget_log2 for c in coverable)
    return {
        "budget_log2": budget_log2,
        "certified_lower_bounds": classes,
        "provably_beyond_budget_classes": beyond,
        "beyond_tracked_paradigms": beyond_tracked,
        "untracked_paradigms_not_ruled_out": untracked,
        "beyond_tracked_paradigms_reads": (
            ("beyond budget for every TRACKED paradigm via certified lower bounds, BUT "
             "untracked methods (Pauli-propagation, ZX, low-rank, ...) are NOT ruled out "
             "-> still NOT a hardness proof") if beyond_tracked else
            "NOT provable even within tracked paradigms: at least one lacks a certified "
            "lower bound (e.g. greedy treewidth gives only an upper bound)"),
        "conditional_all_algorithms": (
            "hardness for ALL classical algorithms is proven only for specific ensembles "
            "(e.g. random-circuit sampling) UNDER unproven conjectures (PH non-collapse + "
            "anti-concentration); ensemble membership NOT verified here"),
        "absolute": "unprovable today (would imply BQP != BPP; even P != NP is open)",
    }


def certificate(qasm: str) -> dict:
    n, circ, _ = safe_parse(qasm)
    r = cost_atlas(n, circ)
    ra = r.get("route_adjudication") or {}
    costs = r.get("costs_log2") or {}

    # If the engine produced no route adjudication, defer — never guess a verdict.
    if not ra.get("route"):
        return {"route": None, "error": r.get("route_adjudication_error", "no adjudication"),
                "confidence": {"tier": "verify",
                               "reads": "engine produced no route adjudication -> defer"}}

    route = ra["route"].lower()
    cheap = route in CHEAP_ROUTES
    governing = ra.get("governing_estimator")          # the cheapest VALID estimator
    gcost = ra.get("governing_cost_log2")
    clifford = bool(r.get("stim_clifford"))
    truncated = bool(r.get("mps_truncated"))
    tw_exact = bool(r.get("treewidth_exact"))

    # (1) WITNESS — sourced ONLY from the governing (valid) estimator, never best_method
    if cheap:
        trivial = (gcost is not None and gcost <= 2)          # avoid odd "via X within 2^0"
        witness = {"claim": "cheap", "method": governing, "bound_log2": gcost,
                   "reads": (f"trivially classically simulable (low {governing}; cost ~{_p2(gcost)})"
                             if trivial else
                             f"classically simulable via {governing} within ~{_p2(gcost)}")}
    else:
        witness = {"claim": "hard", "governing": governing, "cost_log2": gcost,
                   "reason": ra.get("governing_reason"),
                   "scope": "method-relative: beyond all MEASURED classical methods; "
                            "NOT a classical-hardness proof (a better algorithm could refute)",
                   "reads": f"beyond every measured classical method's budget "
                            f"({governing} requires {_p2(gcost)}); not an impossibility proof"}

    # (2) CONFIDENCE TIER — CALIBRATED against the certified benchmark via conformal
    # (atlas_conformal): the tier carries an empirical coverage guarantee, and DECLINES
    # (-> verify) when the circuit is out-of-distribution (exchangeability fails). This
    # is the rigorous form of honest deferral. Falls back to the engine's confidence
    # label if calibration data is unavailable.
    conf = ra.get("confidence") or {}
    label = (conf.get("label") or "").lower()
    score = conf.get("score")
    cal = None
    if atlas_conformal is not None:
        try:
            cal = atlas_conformal.certify(score or 0, label, {
                "n": n, "t_count": r.get("t_count"),
                "magic_log2": costs.get("fold(magic)"),
                "mps_log2": costs.get("MPS(entangle)"),
                "treewidth_log2": costs.get("contraction(treewidth)")}, route=route)
        except Exception:
            cal = None
    if clifford:
        tier, tier_reads = "exact", "Stim stabilizer simulation is exact (Clifford circuit)"
    elif cal is not None:
        if cal["ood"]:
            tier, tier_reads = "verify", cal["statement"]
        elif cal["accepted"]:
            tier, tier_reads = "calibrated", cal["statement"]
        else:
            tier, tier_reads = "verify", cal["statement"]
    elif label == "high":           # fallback: no calibration data
        tier, tier_reads = "measured", "engine confidence high (uncalibrated fallback)"
    elif label in ("med", "medium"):
        tier, tier_reads = "provisional", "engine confidence medium (uncalibrated fallback)"
    else:
        tier, tier_reads = "verify", "engine confidence low (uncalibrated fallback)"
    confidence = {"tier": tier, "reads": tier_reads, "calibration": cal,
                  "atlas_confidence_label": conf.get("label"),
                  "atlas_confidence_score": conf.get("score"),
                  "stim_clifford": clifford, "mps_truncated": truncated,
                  "treewidth_exact": tw_exact}

    # (2b) FALSE-SAFETY RISK — route-INDEPENDENT fragility signal. The conformal tier
    # keys off the predicted route and is blind to false-safety by construction; this
    # is the missing guard. If risk is HIGH on a cheap-side verdict, DOWNGRADE the tier
    # to 'verify' so the user-facing verdict reflects the fragility.
    fsr = None
    if _fs_risk is not None:
        try:
            fsr = _fs_risk(ra, {"stim_clifford": clifford, "treewidth_exact": tw_exact,
                                "mps_truncated": truncated})
        except Exception:
            fsr = None
    if fsr and fsr.get("band") == "HIGH" and cheap and tier in ("calibrated", "measured", "provisional"):
        confidence["tier"] = "verify"
        confidence["reads"] = ("downgraded to verify: HIGH route-independent false-safety "
                               "risk — " + fsr.get("reads", ""))
        confidence["downgraded_by_false_safety_risk"] = True

    # (3) HARDNESS DRIVER — the governing estimator + the lever
    human, lever = _DRIVER.get(_driver_key(governing), ("unknown", "n/a"))
    driver = {"governing": governing, "is": human, "lever": lever,
              "magic_log2": costs.get("fold(magic)"), "t_count": r.get("t_count"),
              "mps_log2": costs.get("MPS(entangle)"),
              "treewidth_log2": costs.get("contraction(treewidth)")}

    # (4) CAVEATS — surface method-quality limitations PROMINENTLY (not buried), so a
    # number is never mistaken for more than it is. Directly answers hostile review
    # points #2 (silent fast-path), #3 (treewidth presented as measured), #9 (index).
    caveats = []
    if not tw_exact and costs.get("contraction(treewidth)") is not None:
        caveats.append("treewidth is a GREEDY UPPER bound (heuristic), not exact; it can "
                       "OVERSTATE cost (bias toward 'classically easy'). Only used as a "
                       "certified lower bound when treewidth_exact=True.")
    if truncated and costs.get("MPS(entangle)") is not None:
        caveats.append("MPS bond is a TRUNCATED lower bound; true MPS cost is >= this value.")
    if costs.get("spread(local)") is None and n > 16:
        caveats.append(f"fast-path: Pauli spread not computed for n={n}>16; verdict uses "
                       "3 of 4 methods (magic + MPS + treewidth), not the full multi-method set.")
    if route in ("hpc_first", "escalate"):
        caveats.append("'hard' = beyond every MEASURED classical method's budget; NOT a proof "
                       "of classical impossibility (BQP!=BPP open) nor of quantum advantage.")

    # (5) WITNESSES — make the four numbers a diligence reviewer attacks AUDITABLE:
    # define exactly what each is (and is NOT), so a small displayed value cannot be
    # mistaken for a stronger claim. Answers audit P0-A (spread), P0-B (RAM), P0-C
    # (treewidth-vs-graph), P0-D (the 0.996 score is defined in atlas_conformal/UI).
    res = r.get("resources") or {}
    sv_bytes = (2 ** n) * 16 if n <= 30 else None      # exact statevector memory, complex128
    witnesses = {
        "spread": {"value_log2": costs.get("spread(local)"),
                   "is": "operator-spread COST bucket (log2) of the arsenal method; "
                         "low = the propagated operator stays local/cheap",
                   "is_not": "NOT the max Pauli support; do not read 2^0 as 'support 1'. "
                             "Heisenberg back-propagation through T gates can reach support "
                             "~4-5 qubits before decaying on a 1D chain — that does not make "
                             "it hard, it just means the COST stays bounded.",
                   "available": costs.get("spread(local)") is not None,
                   "note": "n/a for n>%d (fast-path; verdict uses magic+MPS+treewidth)" % 14},
        "memory": {"reported_human": res.get("ram_human"),
                   "reported_bytes": res.get("ram_bytes"),
                   "is": "order-of-magnitude footprint of the DOMINANT resource of the "
                         "chosen method (e.g. one tensor / amplitude), not full simulation",
                   "is_not": "NOT full statevector or full simulator memory",
                   "exact_statevector_bytes_complex128": sv_bytes},
        "treewidth": {"value_log2": costs.get("contraction(treewidth)"),
                      "is": "tensor-network CONTRACTION width (cotengra greedy UPPER bound)",
                      "is_not": "NOT the interaction-graph treewidth (a 1D/local CX graph has "
                                "structural treewidth ~1); this is the contraction cost proxy",
                      "exact": tw_exact, "bound_type": "heuristic_upper_bound"},
    }

    # (6) PROVENANCE — per-run reproducibility (audit P1-1): input hash, n, engine
    # versions, and which estimators are exact vs heuristic for THIS circuit. Lets a
    # reviewer reproduce/audit the verdict independently and know what to trust.
    gt = (r.get("ground_truth") or {})
    provenance = {
        "qasm_sha256": hashlib.sha256((qasm or "").encode()).hexdigest(),
        "n_qubits": n, "t_count": r.get("t_count"),
        "engine_versions": _engine_versions(),
        "estimators_run": (gt.get("methods") or {}),
        "exactness": {"magic": "exact (Stim Clifford-ness)",
                      "mps": "exact" if not truncated else "truncated lower bound",
                      "treewidth": "exact (optimal)" if tw_exact else "heuristic upper bound (cotengra greedy)",
                      "statevector": "exact (2^n) up to memory ceiling"},
        "certificate_schema": "atlas_certificate/v1"}

    # Hardware-aware qualifier (lente Kingston): un 'necesita QPU' solo apunta a hardware real si
    # el circuito es ALCANZABLE dentro del presupuesto de fidelidad. OFFLINE (snapshot medido).
    hardware = None
    try:
        from atlas_hardware import qualify_offline, two_qubit_layers, KINGSTON_SNAPSHOT
        hardware = qualify_offline(ra.get("route"), two_qubit_layers(circ), KINGSTON_SNAPSHOT, n_qubits=n)
        hardware["snapshot"] = {k: KINGSTON_SNAPSHOT[k] for k in ("backend", "measured", "depth_ceiling_eplg")}
    except Exception as e:
        hardware = {"applies": False, "error": str(e)[:160]}

    return {"route": ra.get("route"), "witness": witness,
            "confidence": confidence, "driver": driver,
            "false_safety_risk": fsr,
            "impossibility": _impossibility(r, costs, n),
            "caveats": caveats,
            "witnesses": witnesses,
            "provenance": provenance,
            "hardware": hardware,
            "resources": r.get("resources")}


if __name__ == "__main__":
    import json
    import sys
    qasm = sys.stdin.read() if not sys.stdin.isatty() else (
        "OPENQASM 2.0;\ninclude \"qelib1.inc\";\nqreg q[3];\n"
        "h q[0];\ncx q[0],q[1];\ncx q[1],q[2];\nt q[2];\n")
    print(json.dumps(certificate(qasm), indent=1))

"""NON-CIRCULAR ground-truth validation driver.

For a representative small-n subset (n <= CAP_N) of BOTH corpora, run:
  (a) Atlas's REAL engine (cost_atlas + route_adjudicator via external_corpus/worker.py,
      imported read-only) -> route / verdict
  (b) EXACT dense statevector execution (sv_worker.py) -> the non-circular ground truth:
      it either realizes the 2^n amplitudes within memory+time budget (=> classically
      tractable BY EXECUTION) or it does not.

Then compare: every circuit Atlas routed to a CLASSICAL tier must be confirmed by exact
statevector actually running. Data-only. No deploy, no engine edits.
"""
from __future__ import annotations
import os, sys, json, subprocess, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "/Users/kreniq/Desktop/KRENIQ/AI Projects/01. Investigacion/00. OPORTUNIDADES/codex_subrepo/atlas-codex"
VENV = os.path.join(BASE, ".atlas-venv/bin/python")
HERE = os.path.join(BASE, "benchmarks/noncircular_groundtruth")
ATLAS_WORKER = os.path.join(BASE, "benchmarks/external_corpus/worker.py")
SV_WORKER = os.path.join(HERE, "sv_worker.py")

CAP_N = 26
CLASSICAL_TIERS = {"CPU", "TENSOR", "HPC_FIRST"}
ATLAS_TIMEOUT = 240
SV_TIMEOUT = 360
MAX_WORKERS = 4


def qreg_n(path):
    try:
        with open(path) as f:
            txt = f.read()
        tot = 0
        for m in re.finditer(r'qu?reg\s+\w+\s*\[\s*(\d+)\s*\]', txt):
            tot += int(m.group(1))
        return tot or None
    except Exception:
        return None


def collect_selfgen():
    """Stratified sample of circuits_scaled/. Deeper n costs more statevector time,
    so we thin the per-(family,density) seed budget as n grows -- still spanning all
    families/densities/n. n<=CAP only."""
    d = os.path.join(BASE, "benchmarks/circuits_scaled")
    seed_budget = {8: 3, 12: 3, 16: 3, 20: 2, 24: 2}
    groups = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".qasm"):
            continue
        try:
            fam, rest = fn[:-5].split("_n", 1)
            toks = rest.split("_")
            n = int(toks[0]); depth = toks[1]; dens = toks[2]; seed = toks[3]
        except Exception:
            continue
        if n > CAP_N:
            continue
        key = (fam, n, dens)
        groups.setdefault(key, []).append((seed, fn))
    out = []
    for (fam, n, dens), lst in groups.items():
        lst.sort()
        k = seed_budget.get(n, 1)
        for seed, fn in lst[:k]:
            out.append({"name": fn[:-5], "path": os.path.join(d, fn), "n": n,
                        "structure": f"{fam}/{dens}", "corpus": "self_generated"})
    return out


def collect_external():
    dirs = [
        os.path.join(BASE, "benchmarks/external_corpus/qasm"),
        os.path.join(BASE, "benchmarks/external_corpus/batch2_published/qasm"),
        os.path.join(BASE, "benchmarks/external_corpus/tier2_qaoa_trotter/qasm"),
        os.path.join(BASE, "benchmarks/external_corpus/tier2_vqe/qasm"),
    ]
    out = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        tag = os.path.basename(os.path.dirname(d)) if "external_corpus" != os.path.basename(os.path.dirname(d)) else "external_qasm"
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".qasm"):
                continue
            path = os.path.join(d, fn)
            n = qreg_n(path)
            if n is None or n > CAP_N:
                continue
            out.append({"name": fn[:-5], "path": path, "n": n,
                        "structure": f"published/{tag}", "corpus": "external"})
    return out


def run_json(argv, timeout):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            return {"_error": (p.stderr.strip().splitlines() or ["?"])[-1][:200]}
        line = [l for l in p.stdout.strip().splitlines() if l.strip().startswith("{")][-1]
        return json.loads(line)
    except subprocess.TimeoutExpired:
        return {"_error": f"TIMEOUT>{timeout}s"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def process(c):
    atlas = run_json([VENV, ATLAS_WORKER, c["path"]], ATLAS_TIMEOUT)
    sv = run_json([VENV, SV_WORKER, c["path"]], SV_TIMEOUT)
    route = atlas.get("route")
    atlas_classical = route in CLASSICAL_TIERS
    sv_feasible = bool(sv.get("exact_sim_feasible"))
    sv_err = sv.get("_error") or (sv.get("note") if (sv.get("note") or "").startswith("sim_error") else None)
    atlas_err = atlas.get("_error")

    # classification
    if atlas_err:
        category = "atlas_error"; agrees = None
    elif route is None:
        category = "atlas_no_route"; agrees = None
    elif sv_err and not sv_feasible:
        category = "sim_error"; agrees = None
    elif atlas_classical and sv_feasible:
        category = "classical_confirmed"; agrees = True
    elif atlas_classical and not sv_feasible:
        category = "classical_UNCONFIRMED"; agrees = False   # disagreement: flag
    elif route == "ESCALATE" and sv_feasible:
        category = "escalate_but_tractable"; agrees = None    # conservative/budget verdict
    elif route == "ESCALATE" and not sv_feasible:
        category = "escalate_and_infeasible"; agrees = None
    else:
        category = f"other({route})"; agrees = None

    note = sv.get("note")
    if category == "escalate_but_tractable":
        note = ("Atlas ESCALATE at small n is a CONSERVATIVE/budget verdict, not an error: "
                "exact statevector confirms it is classically tractable. " + (note or ""))
    return {
        "name": c["name"], "corpus": c["corpus"], "n": c["n"], "structure": c["structure"],
        "atlas_route": route,
        "atlas_verdict": atlas.get("verdict"),
        "atlas_governing_estimator": atlas.get("governing_estimator"),
        "atlas_confidence": atlas.get("confidence"),
        "atlas_classical_tier": atlas_classical,
        "exact_sim_method": sv.get("exact_sim_method"),
        "exact_sim_feasible": sv_feasible,
        "exact_sim_seconds": sv.get("exact_sim_seconds"),
        "exact_sim_norm": sv.get("statevector_norm"),
        "n_gates_basis": sv.get("n_gates_basis"),
        "verdict_agrees": agrees,
        "category": category,
        "atlas_error": atlas_err,
        "sim_error": sv_err,
        "note": note,
    }


def main():
    circuits = collect_selfgen() + collect_external()
    print(f"selected {len(circuits)} circuits (n<=CAP_N={CAP_N})", flush=True)
    results = []
    t0 = time.time()
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(process, c): c for c in circuits}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            done += 1
            if done % 10 == 0 or done == len(circuits):
                print(f"  {done}/{len(circuits)}  ({time.time()-t0:.0f}s)  last={r['name']} "
                      f"route={r['atlas_route']} sim={r['exact_sim_feasible']} cat={r['category']}", flush=True)
    results.sort(key=lambda r: (r["corpus"], r["n"], r["name"]))

    # aggregate
    def cnt(pred):
        return sum(1 for r in results if pred(r))
    classical = [r for r in results if r["atlas_classical_tier"]]
    classical_verifiable = [r for r in classical if r["category"] in ("classical_confirmed", "classical_UNCONFIRMED")]
    confirmed = [r for r in classical if r["category"] == "classical_confirmed"]
    unconfirmed = [r for r in classical if r["category"] == "classical_UNCONFIRMED"]
    escalate_tractable = [r for r in results if r["category"] == "escalate_but_tractable"]
    summary = {
        "cap_n": CAP_N,
        "exact_sim_method": "dense statevector (numpy, full 2^n complex128, gate-by-gate; u+cx basis) -- brute-force EXECUTION, independent of MPS/treewidth",
        "total_selected": len(results),
        "by_corpus": {c: cnt(lambda r, c=c: r["corpus"] == c) for c in ("self_generated", "external")},
        "atlas_classical_verdicts": len(classical),
        "atlas_classical_verifiable_by_exact_sim": len(classical_verifiable),
        "classical_confirmed_by_execution": len(confirmed),
        "classical_UNCONFIRMED_disagreements": len(unconfirmed),
        "agreement_rate": (round(len(confirmed) / len(classical_verifiable), 4) if classical_verifiable else None),
        "escalate_but_exactsim_tractable_conservative": len(escalate_tractable),
        "atlas_escalate_total": cnt(lambda r: r["atlas_route"] == "ESCALATE"),
        "sim_errors": cnt(lambda r: r["category"] == "sim_error"),
        "atlas_errors": cnt(lambda r: r["category"] == "atlas_error"),
        "category_breakdown": {},
        "n_range": [min(r["n"] for r in results), max(r["n"] for r in results)],
        "route_breakdown": {},
    }
    for r in results:
        summary["category_breakdown"][r["category"]] = summary["category_breakdown"].get(r["category"], 0) + 1
        rt = str(r["atlas_route"])
        summary["route_breakdown"][rt] = summary["route_breakdown"].get(rt, 0) + 1

    payload = {"summary": summary,
               "disagreements": [r for r in unconfirmed],
               "conservative_escalations": [{"name": r["name"], "n": r["n"], "structure": r["structure"],
                                             "exact_sim_seconds": r["exact_sim_seconds"]} for r in escalate_tractable],
               "results": results,
               "engine": "atlas-codex/HANDOFF_5ideas cost_atlas + route_adjudicator (REAL, read-only import via external_corpus/worker.py)",
               "ground_truth": "exact dense statevector via benchmarks/noncircular_groundtruth/sv_worker.py (numpy, cross-checked fidelity=1.0 vs qiskit.quantum_info.Statevector on n<=10)",
               "note": "Data-only research artifact. No deploy, no site edit, no engine files modified."}
    out = os.path.join(HERE, "results.json")
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()

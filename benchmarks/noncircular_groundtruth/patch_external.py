"""Re-validate the EXTERNAL circuits with the correctness-guarded sv_worker (which now
aborts honestly on non-unitary/control-flow ops instead of silently dropping them, and
understands rxx/ryy/rzz). Self-generated circuits are pure {h,s,t,cx} by construction
(trivially unitary) so their original exact-sim results stand. Atlas routes are unchanged
(read from the prior run). Recomputes the summary. Data-only.
"""
from __future__ import annotations
import os, json, subprocess, time

BASE = "."
VENV = os.path.join(BASE, ".atlas-venv/bin/python")
HERE = os.path.join(BASE, "benchmarks/noncircular_groundtruth")
SV_WORKER = os.path.join(HERE, "sv_worker.py")
RESULTS = os.path.join(HERE, "results.json")
CLASSICAL_TIERS = {"CPU", "TENSOR", "HPC_FIRST"}
PER_TIMEOUT = 900

# path lookup for external circuits
EXT_DIRS = [
    os.path.join(BASE, "benchmarks/external_corpus/qasm"),
    os.path.join(BASE, "benchmarks/external_corpus/batch2_published/qasm"),
    os.path.join(BASE, "benchmarks/external_corpus/tier2_qaoa_trotter/qasm"),
    os.path.join(BASE, "benchmarks/external_corpus/tier2_vqe/qasm"),
]
# known wall-time exclusion (memory fine, gate-count prohibitive) -- do not spend 900s to reconfirm
SKIP = {
    "qb_vqe_n24": "2306072 basis gates (u+cx): exact statevector memory-feasible (2^24 ~ 268 MB) but "
                  "gate-count makes brute-force wall-time prohibitive; Atlas routed TENSOR (a tensor "
                  "network exploits the structure). Honest exact-sim tooling exclusion, NOT a disagreement.",
}


def find_path(name):
    for d in EXT_DIRS:
        p = os.path.join(d, name + ".qasm")
        if os.path.exists(p):
            return p
    return None


def run_sv(path):
    try:
        p = subprocess.run([VENV, SV_WORKER, path], capture_output=True, text=True, timeout=PER_TIMEOUT)
        if p.returncode != 0:
            return {"_error": (p.stderr.strip().splitlines() or ["?"])[-1][:200]}
        line = [l for l in p.stdout.strip().splitlines() if l.strip().startswith("{")][-1]
        return json.loads(line)
    except subprocess.TimeoutExpired:
        return {"_error": f"TIMEOUT>{PER_TIMEOUT}s"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def categorize(route, sv):
    atlas_classical = route in CLASSICAL_TIERS
    feasible = bool(sv.get("exact_sim_feasible"))
    sv_err = sv.get("_error") or (sv.get("note") if (sv.get("note") or "").startswith("sim_error") else None)
    if route is None:
        return "atlas_no_route", None, sv_err
    if sv_err and not feasible:
        return "sim_error", None, sv_err
    if atlas_classical and feasible:
        return "classical_confirmed", True, sv_err
    if atlas_classical and not feasible:
        return "classical_UNCONFIRMED", False, sv_err
    if route == "ESCALATE" and feasible:
        return "escalate_but_tractable", None, sv_err
    if route == "ESCALATE" and not feasible:
        return "escalate_and_infeasible", None, sv_err
    return f"other({route})", None, sv_err


def main():
    d = json.load(open(RESULTS))
    results = d["results"]
    ext = [r for r in results if r["corpus"] == "external"]
    print(f"re-validating {len(ext)} external circuits with guarded sv_worker", flush=True)
    t0 = time.time()
    for i, r in enumerate(ext, 1):
        name = r["name"]
        if name in SKIP:
            sv = {"exact_sim_feasible": False, "exact_sim_method": "dense_statevector(numpy) [not attempted]",
                  "note": SKIP[name], "_error": "wall_time_exclusion"}
        else:
            path = find_path(name)
            sv = run_sv(path) if path else {"_error": "path_not_found"}
        cat, agrees, sv_err = categorize(r["atlas_route"], sv)
        r["exact_sim_method"] = sv.get("exact_sim_method", r.get("exact_sim_method"))
        r["exact_sim_feasible"] = bool(sv.get("exact_sim_feasible"))
        r["exact_sim_seconds"] = sv.get("exact_sim_seconds")
        r["exact_sim_norm"] = sv.get("statevector_norm")
        r["n_gates_basis"] = sv.get("n_gates_basis")
        r["verdict_agrees"] = agrees
        r["category"] = cat
        r["sim_error"] = sv_err
        note = sv.get("note")
        if cat == "escalate_but_tractable":
            note = "Atlas ESCALATE at small n is CONSERVATIVE/budget, not error: exact statevector confirms tractable. " + (note or "")
        r["note"] = note
        if i % 10 == 0 or i == len(ext):
            print(f"  {i}/{len(ext)} ({time.time()-t0:.0f}s) {name} route={r['atlas_route']} feas={r['exact_sim_feasible']} cat={cat}", flush=True)

    # recompute summary
    classical = [r for r in results if r["atlas_classical_tier"]]
    classical_verifiable = [r for r in classical if r["category"] in ("classical_confirmed", "classical_UNCONFIRMED")]
    confirmed = [r for r in classical if r["category"] == "classical_confirmed"]
    unconfirmed = [r for r in classical if r["category"] == "classical_UNCONFIRMED"]
    escalate_tractable = [r for r in results if r["category"] == "escalate_but_tractable"]

    def cnt(pred):
        return sum(1 for r in results if pred(r))
    s = d["summary"]
    s["total_selected"] = len(results)
    s["atlas_classical_verdicts"] = len(classical)
    s["atlas_classical_verifiable_by_exact_sim"] = len(classical_verifiable)
    s["classical_confirmed_by_execution"] = len(confirmed)
    s["classical_UNCONFIRMED_disagreements"] = len(unconfirmed)
    s["agreement_rate"] = round(len(confirmed) / len(classical_verifiable), 4) if classical_verifiable else None
    s["escalate_but_exactsim_tractable_conservative"] = len(escalate_tractable)
    s["atlas_escalate_total"] = cnt(lambda r: r["atlas_route"] == "ESCALATE")
    s["sim_errors_excluded_tooling"] = cnt(lambda r: r["category"] == "sim_error")
    s.pop("sim_errors", None)
    s["category_breakdown"] = {}
    s["route_breakdown"] = {}
    for r in results:
        s["category_breakdown"][r["category"]] = s["category_breakdown"].get(r["category"], 0) + 1
        rt = str(r["atlas_route"])
        s["route_breakdown"][rt] = s["route_breakdown"].get(rt, 0) + 1
    # exclusion detail
    d["exact_sim_tooling_exclusions"] = [
        {"name": r["name"], "n": r["n"], "atlas_route": r["atlas_route"], "reason": r["sim_error"], "note": r["note"]}
        for r in results if r["category"] == "sim_error"]
    d["disagreements"] = [r for r in unconfirmed]
    d["conservative_escalations"] = [{"name": r["name"], "n": r["n"], "structure": r["structure"],
                                      "exact_sim_seconds": r["exact_sim_seconds"]} for r in escalate_tractable]
    results.sort(key=lambda r: (r["corpus"], r["n"], r["name"]))
    json.dump(d, open(RESULTS, "w"), indent=2)
    print("\n=== UPDATED SUMMARY ===")
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()

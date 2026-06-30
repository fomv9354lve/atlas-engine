"""Run Atlas's REAL cost_atlas + route_adjudicator on ONE qasm file and print a
JSON line. Isolated in its own process so a heavy contraction (or the known
cost_atlas DoS on adversarial inputs) can be killed by a timeout without taking
down the whole corpus run. Bypasses the web handler's n-cap by calling
cost_atlas directly (research-only; the live cap is untouched)."""
from __future__ import annotations
import sys, json, time, os

ENGINE = "/Users/kreniq/Desktop/KRENIQ/AI Projects/01. Investigacion/00. OPORTUNIDADES/codex_subrepo/atlas-codex/HANDOFF_5ideas"
sys.path.insert(0, ENGINE)
os.chdir(ENGINE)  # ground_truth/atlas use relative 'src' path

from atlas import safe_parse, cost_atlas  # noqa: E402


def main():
    path = sys.argv[1]
    with open(path) as f:
        text = f.read()
    t0 = time.time()
    n, circ, warns = safe_parse(text)
    r = cost_atlas(n, circ)
    dt = time.time() - t0
    ra = r.get("route_adjudication") or {}
    costs = r.get("costs_log2") or {}
    out = {
        "n": n,
        "t_count": r.get("t_count"),
        "magic_log2": costs.get("fold(magic)"),
        "mps_bond_log2": costs.get("MPS(entangle)"),
        "mps_truncated": r.get("mps_truncated"),
        "treewidth_log2": costs.get("contraction(treewidth)"),
        "treewidth_exact": r.get("treewidth_exact"),
        "stim_clifford": r.get("stim_clifford"),
        "best_method": r.get("best_method"),
        "union_cost_log2": r.get("union_cost_log2"),
        "verdict": r.get("verdict"),
        "route": ra.get("route"),
        "governing_estimator": ra.get("governing_estimator"),
        "governing_cost_log2": ra.get("governing_cost_log2"),
        "confidence": (ra.get("confidence") or {}).get("label"),
        "confidence_score": (ra.get("confidence") or {}).get("score"),
        "single_estimator_baselines": ra.get("single_estimator_baselines"),
        "n_parse_warnings": len(warns),
        "elapsed_s": round(dt, 2),
    }
    print(json.dumps(out))


if __name__ == "__main__":
    main()

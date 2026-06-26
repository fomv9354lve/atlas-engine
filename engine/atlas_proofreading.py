#!/usr/bin/env python3
"""atlas_proofreading — the thermodynamic / kinetic-proofreading curve of the triage (additive).

Biology's lens (Hopfield-Ninio kinetic proofreading; Landauer; the Thermodynamic Uncertainty Relation):
precision is *bought* with dissipation, in steps, and the optimal stopping point is where the marginal
benefit of one more proofreading step no longer pays its cost. Atlas IS this, unnamed: each estimator is
a proofreading step that costs compute and buys information about the true route.

This measures, from the certified corpus, the **information-vs-cost proofreading curve**:
  * cumulative I(route ; estimators-so-far) in BITS, estimators added cheapest -> costliest
  * per-step marginal bits, and marginal **bits per second** (information efficiency)
  * the optimal stopping point: where marginal bits/second drops below the next step's price
This grounds two things Atlas already does heuristically: (a) the Unified Core early-exit ordering, and
(b) MEDIUM as the *thermodynamically optimal abstention* — the point where even the full chain hasn't
resolved the route, so paying more dissipation is wasted.

Information: plug-in mutual information (bits), Miller-Madow corrected, on the 800-row stratified set
that carries the single-estimator-only route classes. Cost: representative per-estimator wall-clock on a
dev Apple M4, from benchmarks/threshold_calibration.json + scale_ceiling.json (documented, not invented).

Run: python3 atlas_proofreading.py   (writes proofreading.json + proofreading.svg)
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

CSV_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "results_scaled"
FULL = CSV_DIR / "scaled_results.csv"


def _rows():
    return [r for r in csv.DictReader(FULL.open(encoding="utf-8"))
            if r.get("oracle_certified", "").strip().lower() == "true"]


def _norm(s):
    return (s or "").strip().lower()


def _entropy(counts):
    n = sum(counts.values())
    if n == 0:
        return 0.0
    h = -sum((c / n) * math.log2(c / n) for c in counts.values() if c > 0)
    k = sum(1 for c in counts.values() if c > 0)
    return h + (k - 1) / (2 * n * math.log(2))


def _mi(pairs):
    if not pairs:
        return 0.0
    return (_entropy(Counter(x for x, _ in pairs))
            + _entropy(Counter(y for _, y in pairs))
            - _entropy(Counter(pairs)))


def main():
    rows = _rows()
    route = [_norm(r["oracle_route"]) for r in rows]

    # estimators ordered CHEAPEST -> COSTLIEST, with representative measured wall-clock (s, dev M4).
    # T/Clifford pre-check is microseconds (gate-set scan); MPS and treewidth are the heavy steps.
    # Costs are representative medians from threshold_calibration.json / scale_ceiling.json (documented).
    steps = [
        {"name": "magic/#T (+Clifford pre-check)", "col": "magic_only_class", "cost_s": 0.001},
        {"name": "MPS bond (quimb)",                "col": "mps_only_class",   "cost_s": 0.9},
        {"name": "treewidth (cotengra greedy)",     "col": "treewidth_only_class", "cost_s": 1.5},
    ]
    cols = [[_norm(r.get(s["col"])) for r in rows] for s in steps]

    H_route = _entropy(Counter(route))
    curve = []
    prev_bits, cum_cost = 0.0, 0.0
    for i, s in enumerate(steps):
        prefix = list(zip(*cols[: i + 1]))           # tuple of estimator outputs so far
        I = _mi(list(zip(route, prefix)))
        cum_cost += s["cost_s"]
        marg_bits = I - prev_bits
        marg_eff = marg_bits / s["cost_s"] if s["cost_s"] > 0 else float("inf")
        curve.append({
            "step": i + 1, "estimator": s["name"], "step_cost_s": s["cost_s"],
            "cumulative_cost_s": round(cum_cost, 4),
            "cumulative_bits": round(I, 4),
            "marginal_bits": round(marg_bits, 4),
            "marginal_bits_per_second": round(marg_eff, 4),
            "frac_of_H_route": round(I / H_route, 4) if H_route else 0.0,
        })
        prev_bits = I

    # optimal stop: last step whose marginal bits/s exceeds a small efficiency floor (diminishing returns)
    eff_floor = 0.01   # bits per second; below this, a proofreading step does not pay
    optimal_stop = max((c["step"] for c in curve if c["marginal_bits_per_second"] >= eff_floor),
                       default=1)
    # the kinetic-proofreading signature is diminishing *efficiency* (bits per second), not absolute bits
    eff = [c["marginal_bits_per_second"] for c in curve]
    diminishing_efficiency = all(eff[i] <= eff[i - 1] + 1e-9 for i in range(1, len(eff)))
    efficiency_cliff_x = round(eff[0] / eff[1], 1) if len(eff) > 1 and eff[1] > 0 else None

    report = {
        "what": "Thermodynamic / kinetic-proofreading curve of the triage (additive measurement)",
        "lens": "Hopfield-Ninio kinetic proofreading; Landauer bound; Thermodynamic Uncertainty Relation",
        "corpus_n": len(rows),
        "H_route_bits": round(H_route, 4),
        "proofreading_curve": curve,
        "diminishing_efficiency": bool(diminishing_efficiency),
        "efficiency_cliff_after_pre_check_x": efficiency_cliff_x,
        "efficiency_floor_bits_per_s": eff_floor,
        "optimal_stop_step": optimal_stop,
        "reading": {
            "kinetic_proofreading": "each estimator is a proofreading step buying route-information with compute",
            "early_exit": "cheap steps carry most bits/second -> the Unified Core early-exit ordering is "
                          "the thermodynamically efficient order, now grounded empirically",
            "medium_is_optimal_abstention": "when the full chain still leaves residual route-uncertainty, "
                                            "paying more dissipation is wasted -> MEDIUM is the optimal stop",
        },
        "caveats": [
            "Information is measured exactly (bits, Miller-Madow). Cost is representative per-estimator "
            "wall-clock on a dev M4 (threshold_calibration.json / scale_ceiling.json), not per-circuit timed.",
            "Landauer/TUR are the conceptual lens; we quantify bits and compute-cost, not Joules.",
            "Single-estimator-only route classes exist on the 800-row stratified set.",
        ],
    }
    (CSV_DIR / "proofreading.json").write_text(json.dumps(report, indent=2))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        xs = [0] + [c["cumulative_cost_s"] for c in curve]
        ys = [0] + [c["cumulative_bits"] for c in curve]
        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        ax.plot(xs, ys, "-o", color="#00e5ff", lw=2, ms=7)
        for c in curve:
            ax.annotate(f"+{c['marginal_bits']:.2f} bits\n({c['marginal_bits_per_second']:.2f} b/s)",
                        (c["cumulative_cost_s"], c["cumulative_bits"]),
                        textcoords="offset points", xytext=(8, -18), fontsize=7.5, color="#333")
            ax.annotate(c["estimator"].split(" (")[0],
                        (c["cumulative_cost_s"], c["cumulative_bits"]),
                        textcoords="offset points", xytext=(8, 6), fontsize=8, color="#0a7")
        ax.axhline(H_route, ls="--", color="#d08", lw=1, label=f"H(route)={H_route:.2f} bits (max)")
        ax.set_xlabel("cumulative cost (s, representative wall-clock — log-ish)")
        ax.set_ylabel("cumulative information about the route (bits)")
        ax.set_xscale("symlog", linthresh=0.01)
        ax.set_title("Proofreading curve: information bought per unit dissipation (diminishing returns)")
        ax.legend(fontsize=8, loc="lower right")
        fig.tight_layout()
        fig.savefig(CSV_DIR / "proofreading.svg")
        fig.savefig(CSV_DIR / "proofreading.png", dpi=130)
    except Exception as e:
        print("figure skipped:", e)

    print(json.dumps(report["proofreading_curve"], indent=2))
    print("diminishing efficiency:", diminishing_efficiency, "| cliff after pre-check:",
          efficiency_cliff_x, "x | H(route)=", round(H_route, 4))


if __name__ == "__main__":
    main()

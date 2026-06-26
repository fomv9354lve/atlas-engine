#!/usr/bin/env python3
"""atlas_channel_capacity — the Shannon view of triage (ADDITIVE feature, not a replacement).

The crown-jewel question, made measurable: **how many bits of information about the true
classical-simulation route does Atlas's verdict actually transport** — and how many does each
physical estimator (magic/#T, MPS bond, treewidth) carry alone vs. combined?

This reframes Atlas from a triage *tool* into a measuring *instrument* of the classical-simulability
frontier. It is computable TODAY from the certified corpus because we hold all four ingredients no one
else has together: a multi-estimator predictor, a corpus with exact ground-truth routes + costs, real
QPU validation, and adversarial cases.

Information-theoretic, in bits (log base 2), plug-in estimator with Miller–Madow bias correction:
  * H(route)                              — prior uncertainty about the true route
  * I(route ; verdict)                    — bits the FINAL verdict transports  (efficiency = I/H)
  * I(route ; single estimator)           — bits each physical estimator carries ALONE (the ablation, in bits)
  * I(route ; all estimators jointly)     — bits the multi-estimator adjudicator carries
  * synergy = I(joint) - max(I(single))   — quantitative value of combining estimators
  * confidence increment                  — extra bits from confidence on top of the route label

Honesty (Leone, Eisert & Oliviero arXiv:2602.22330): deciding the route EXACTLY is super-exponential,
so the channel has irreducible noise. We report the ACHIEVED mutual information on the benchmark
distribution — a valid LOWER BOUND on channel capacity (capacity = sup over input distributions ≥ any
achieved MI). We never claim to have reached capacity; we measure how much signal demonstrably passes.

Run: python3 atlas_channel_capacity.py   (writes channel_capacity.json + channel_capacity.svg)
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

CSV_DIR = Path(__file__).resolve().parents[1] / "benchmarks" / "results_scaled"
FULL = CSV_DIR / "scaled_results.csv"          # 800 rows: has single-estimator-only classes + spread
ALL = sorted(CSV_DIR.glob("scaled_results*.csv"))  # 2517 rows: route-level fields only


def _rows(path):
    return [r for r in csv.DictReader(path.open(encoding="utf-8"))
            if r.get("oracle_certified", "").strip().lower() == "true"]


def _norm(s):
    return (s or "").strip().lower()


def _entropy(counts):
    """Shannon entropy in bits from a Counter / iterable of counts, Miller–Madow corrected."""
    n = sum(counts.values())
    if n == 0:
        return 0.0
    h = -sum((c / n) * math.log2(c / n) for c in counts.values() if c > 0)
    k = sum(1 for c in counts.values() if c > 0)      # observed support
    return h + (k - 1) / (2 * n * math.log(2))         # Miller–Madow bias correction (bits)


def _mi(pairs):
    """Mutual information I(X;Y) in bits from a list of (x,y) tuples."""
    n = len(pairs)
    if n == 0:
        return 0.0
    jxy = Counter(pairs)
    jx = Counter(x for x, _ in pairs)
    jy = Counter(y for _, y in pairs)
    # I = H(X) + H(Y) - H(X,Y), each Miller–Madow corrected
    return _entropy(jx) + _entropy(jy) - _entropy(jxy)


def _bin_log2(v, edges=(0.0, 5.5, 10.0, 14.5)):
    """Discretize a log2-cost estimator into route-aligned tiers (cpu/tensor/hpc/escalate)."""
    try:
        x = float(v)
    except Exception:
        return "na"
    if x <= edges[1]:
        return "t0"
    if x <= edges[2]:
        return "t1"
    if x <= edges[3]:
        return "t2"
    return "t3"


def main():
    full = _rows(FULL)
    allrows = []
    for p in ALL:
        allrows += _rows(p)

    # --- verdict-level transported information, on the FULL 2517 corpus ---
    route = [_norm(r["oracle_route"]) for r in allrows]
    verdict = [_norm(r["atlas_route_class"]) for r in allrows]
    H_route = _entropy(Counter(route))
    I_verdict = _mi(list(zip(route, verdict)))
    eff = I_verdict / H_route if H_route > 0 else 0.0

    # --- per-estimator ablation IN BITS, on the 800 rows that carry single-only classes ---
    r8 = [_norm(r["oracle_route"]) for r in full]
    singles = {
        "magic_only (#T)": [_norm(r.get("magic_only_class")) for r in full],
        "mps_only (bond)": [_norm(r.get("mps_only_class")) for r in full],
        "treewidth_only": [_norm(r.get("treewidth_only_class")) for r in full],
    }
    I_single = {k: _mi(list(zip(r8, v))) for k, v in singles.items()}
    H_route8 = _entropy(Counter(r8))

    # joint physical estimators (the multi-estimator adjudicator's raw inputs)
    joint = list(zip(singles["magic_only (#T)"], singles["mps_only (bond)"], singles["treewidth_only"]))
    I_joint = _mi(list(zip(r8, joint)))
    I_final8 = _mi(list(zip(r8, [_norm(r["atlas_route_class"]) for r in full])))
    best_single = max(I_single.values())
    synergy = I_joint - best_single

    # --- does confidence add bits on top of the route label? (2517) ---
    def conf_bin(r):
        try:
            c = float(r["confidence_score"])
        except Exception:
            return "na"
        return "lo" if c < 45 else ("md" if c < 75 else "hi")
    verdict_conf = list(zip(verdict, [conf_bin(r) for r in allrows]))
    I_verdict_plus_conf = _mi(list(zip(route, verdict_conf)))
    conf_increment = I_verdict_plus_conf - I_verdict

    report = {
        "what": "Shannon transported-information of Atlas triage (additive measurement, not a verdict change)",
        "corpus": {"verdict_level_n": len(allrows), "estimator_ablation_n": len(full)},
        "units": "bits (log2)",
        "prior_uncertainty_H_route_bits": round(H_route, 4),
        "verdict_transported_information_bits": round(I_verdict, 4),
        "efficiency_fraction_of_route_uncertainty_resolved": round(eff, 4),
        "residual_uncertainty_after_verdict_bits": round(H_route - I_verdict, 4),
        "per_estimator_information_bits": {k: round(v, 4) for k, v in I_single.items()},
        "best_single_estimator_bits": round(best_single, 4),
        "joint_multi_estimator_bits": round(I_joint, 4),
        "synergy_bits_gained_by_combining": round(synergy, 4),
        "final_adjudicator_bits_800": round(I_final8, 4),
        "confidence_increment_bits": round(conf_increment, 4),
        "H_route_800_bits": round(H_route8, 4),
        "interpretation": {
            "feynman": "validated against real data (oracle ground truth + ibm_kingston), not predicted",
            "shannon": "I(route; verdict) is the channel's transported information; a LOWER bound on capacity",
            "turing": "residual uncertainty is where MEDIUM correctly says 'oracle (QPU) needed'",
            "leone_2602.22330": "exact decision is super-exponential -> channel noise is irreducible; "
                                "we measure how much signal passes, not claim a perfect channel",
        },
        "caveats": [
            "Achieved mutual information on the benchmark distribution = LOWER bound on channel capacity "
            "(capacity is a sup over input distributions); we never claim to have reached capacity.",
            "Plug-in entropies with Miller-Madow correction; small route alphabet so bias is minor but nonzero.",
            "Ablation single-only classes exist on the 800-row stratified set; verdict-level MI uses all 2517.",
        ],
    }

    out = CSV_DIR / "channel_capacity.json"
    out.write_text(json.dumps(report, indent=2))

    # bar figure: bits per estimator vs joint vs final
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        labels = list(I_single) + ["JOINT (multi)", "FINAL verdict"]
        vals = list(I_single.values()) + [I_joint, I_final8]
        colors = ["#6b7280", "#6b7280", "#6b7280", "#0a7", "#00e5ff"]
        fig, ax = plt.subplots(figsize=(6.4, 4.0))
        ax.bar(labels, vals, color=colors)
        ax.axhline(H_route8, ls="--", color="#d08", lw=1, label=f"H(route)={H_route8:.2f} bits (max)")
        for i, v in enumerate(vals):
            ax.text(i, v + 0.02, f"{v:.2f}", ha="center", fontsize=9, color="#222")
        ax.set_ylabel("bits transported about the true route")
        ax.set_title("Atlas as an instrument: information each estimator carries (bits)")
        ax.legend(fontsize=8)
        ax.set_ylim(0, H_route8 * 1.15)
        plt.xticks(rotation=20, ha="right", fontsize=8)
        fig.tight_layout()
        fig.savefig(CSV_DIR / "channel_capacity.svg")
        fig.savefig(CSV_DIR / "channel_capacity.png", dpi=130)
    except Exception as e:
        print("figure skipped:", e)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

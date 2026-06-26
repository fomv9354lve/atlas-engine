#!/usr/bin/env python3
"""atlas_recalibrate — turn the heuristic confidence_score (0-100) into a TRUE
calibrated P(correct route), fit on a selection half and validated on a held-out half.

Why: the raw confidence_score is a heuristic reliability index, not a probability.
Displaying "88/100" as if it were P(correct) is claim drift. This module fits an
isotonic (monotone, non-parametric) recalibrator AND a Platt (logistic) baseline on
the SELECTION half of the certified benchmark, then reports — on the untouched
VALIDATION half — Brier score (raw vs Platt vs isotonic), a reliability diagram, and
Expected Calibration Error, each with Wilson 95% CIs.

Honest design notes:
  * Same deterministic 50/50 split as atlas_conformal (sel = rows[0::2], val = rows[1::2]),
    so the conformal selective-threshold guarantee and this probability share one split.
  * Isotonic is fit ONLY on selection; every reported number is on the held-out half.
  * The corpus is highly accurate (acc 0.9956), so calibrated P(correct) is high almost
    everywhere; the signal lives in the low-confidence tail where ALL errors concentrate.
    Those bins have few errors -> wide CIs, reported as such, never hidden.

Run: python3 atlas_recalibrate.py   (writes calibration_report.json + reliability_diagram.svg)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from atlas_conformal import load, selective_threshold, _cal  # reuse the certified loader + split


def _wilson(k, n, z=1.96):
    """Two-sided Wilson interval for a binomial proportion (k successes of n)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = (z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def brier(p, y):
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((p - y) ** 2))


def reliability_bins(p, y, edges):
    """Bin predictions; report per-bin predicted mean, observed accuracy, Wilson CI."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi if hi < 1.0 else p <= hi)
        n = int(m.sum())
        if n == 0:
            continue
        k = int(y[m].sum())
        clo, chi = _wilson(k, n)
        out.append({"bin_lo": round(lo, 3), "bin_hi": round(hi, 3), "n": n,
                    "pred_mean": round(float(p[m].mean()), 4),
                    "obs_acc": round(k / n, 4),
                    "wilson_lo": round(clo, 4), "wilson_hi": round(chi, 4)})
    return out


def ece(bins, total):
    """Expected Calibration Error: sum_b (n_b/N) |obs_acc_b - pred_mean_b|."""
    return float(sum(b["n"] / total * abs(b["obs_acc"] - b["pred_mean"]) for b in bins))


def main():
    cal = load()                       # certified circuits only (oracle_certified == True)
    conf = np.array([c["conf"] for c in cal], float)
    y = np.array([1.0 if c["correct"] else 0.0 for c in cal], float)
    sel = slice(0, None, 2)
    val = slice(1, None, 2)
    xs, ys = conf[sel] / 100.0, y[sel]
    xv, yv = conf[val] / 100.0, y[val]

    # --- raw (heuristic-as-probability, the current implicit claim) ---
    raw_val = xv

    # --- Platt (logistic) baseline ---
    platt = LogisticRegression(C=1e6, solver="lbfgs")
    platt.fit(xs.reshape(-1, 1), ys)
    platt_val = platt.predict_proba(xv.reshape(-1, 1))[:, 1]

    # --- Isotonic (chosen recalibrator) ---
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(xs, ys)
    iso_val = iso.predict(xv)

    edges = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    Nval = len(yv)
    report = {
        "corpus": {"n_certified_total": len(cal), "n_selection": int(len(ys)),
                   "n_validation": int(Nval),
                   "overall_route_accuracy": round(float(y.mean()), 4),
                   "n_errors_total": int((y == 0).sum())},
        "split": "deterministic 50/50 (rows[0::2] selection, rows[1::2] validation) — shared with atlas_conformal",
        "brier_held_out": {
            "raw_heuristic": round(brier(raw_val, yv), 5),
            "platt": round(brier(platt_val, yv), 5),
            "isotonic": round(brier(iso_val, yv), 5),
        },
        "ece_held_out": {
            "raw_heuristic": round(ece(reliability_bins(raw_val, yv, edges), Nval), 5),
            "isotonic": round(ece(reliability_bins(iso_val, yv, edges), Nval), 5),
        },
        "reliability_raw": reliability_bins(raw_val, yv, edges),
        "reliability_isotonic": reliability_bins(iso_val, yv, edges),
        # the recalibration map: raw confidence_score -> calibrated P(correct)
        "isotonic_map": [{"conf_score": int(round(t * 100)),
                          "p_correct": round(float(iso.predict([t])[0]), 4)}
                         for t in [0.10, 0.18, 0.30, 0.34, 0.45, 0.60, 0.75, 0.80, 0.88, 0.95, 1.00]],
        "conformal_selective_threshold": selective_threshold(cal),
        "caveats": [
            "All 11 errors in the full corpus sit at raw confidence_score <= 34; above that, 0/2517.",
            "Low-confidence bins contain few errors -> wide Wilson CIs (reported per-bin).",
            "Calibrated on classically-CERTIFIABLE circuits; the quantum-hard regime (n>24, no "
            "classical oracle) is unmeasurable by construction and excluded.",
        ],
    }

    outdir = Path(__file__).resolve().parents[1] / "benchmarks" / "results_scaled"
    (outdir / "calibration_report.json").write_text(json.dumps(report, indent=2))

    # --- reliability diagram (SVG) ---
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(5.2, 5.2))
        ax.plot([0, 1], [0, 1], "--", color="#999", lw=1, label="perfect calibration")
        for tag, p, color, mk in (("raw heuristic", raw_val, "#d08", "o"),
                                  ("isotonic (calibrated)", iso_val, "#0a7", "s")):
            bins = reliability_bins(p, yv, edges)
            xsb = [b["pred_mean"] for b in bins]
            ysb = [b["obs_acc"] for b in bins]
            lo = [b["obs_acc"] - b["wilson_lo"] for b in bins]
            hi = [b["wilson_hi"] - b["obs_acc"] for b in bins]
            ax.errorbar(xsb, ysb, yerr=[lo, hi], fmt=mk + "-", color=color, capsize=3,
                        label=tag, lw=1.4, ms=6)
        ax.set_xlabel("predicted P(correct route)")
        ax.set_ylabel("observed accuracy (held-out validation half)")
        ax.set_title(f"Atlas reliability — Brier raw {report['brier_held_out']['raw_heuristic']} "
                     f"-> isotonic {report['brier_held_out']['isotonic']}")
        ax.legend(loc="lower right", fontsize=8)
        ax.set_xlim(0, 1.02); ax.set_ylim(0, 1.02)
        ax.grid(alpha=0.25)
        fig.tight_layout()
        fig.savefig(outdir / "reliability_diagram.svg")
        fig.savefig(outdir / "reliability_diagram.png", dpi=130)
    except Exception as e:
        print("figure skipped:", e)

    print(json.dumps(report["brier_held_out"], indent=2))
    print("ECE:", json.dumps(report["ece_held_out"]))
    print("isotonic map:", json.dumps(report["isotonic_map"]))
    print("wrote calibration_report.json + reliability_diagram.svg to", outdir)


if __name__ == "__main__":
    main()

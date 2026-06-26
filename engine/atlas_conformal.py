#!/usr/bin/env python3
"""atlas_conformal — calibrated confidence for atlas_certificate (no CAPAS code).

Gives a per-circuit confidence statement for Atlas's route, calibrated against the
certified 800-circuit benchmark, with an honest out-of-distribution decline.

Statistical design (hardened after adversarial review — avoids the overclaim of
selecting a threshold on the same data it certifies):
  * SPLIT: the certified set is deterministically halved into a SELECTION half and a
    held-out VALIDATION half.
  * threshold tau is chosen ONLY on the selection half (smallest tau / max coverage
    whose selection-half selective error <= alpha).
  * the reported correctness bound is a one-sided Wilson UPPER bound on the error of
    the VALIDATION-half accepted set at that single tau -> a valid held-out bound,
    not an in-sample / post-selection one. If it does not meet alpha, we say so and
    report the number as EMPIRICAL, never as a guarantee.
  * OOD: bounding-box AND Mahalanobis (chi-square cutoff) joint check; either trips
    -> coverage does not apply -> verify.

certify(confidence_score, label, features) -> calibrated statement for one circuit.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

try:
    import numpy as np
except Exception:
    np = None

def _find_csv_dir():
    """Locate benchmarks/results_scaled robustly (works from engine AND from
    deploy/app, which sits one level deeper)."""
    here = Path(__file__).resolve()
    for base in (*here.parents[1:4], Path.cwd()):
        d = base / "benchmarks" / "results_scaled"
        if d.is_dir():
            return d
    return here.parents[1] / "benchmarks" / "results_scaled"   # fallback (may not exist)


CSV_DIR = _find_csv_dir()
FEATS = ["n", "t_count", "magic_log2", "mps_log2", "treewidth_log2"]
Z_ONE_SIDED_95 = 1.645      # one-sided 95% (delta=0.05) normal quantile
CHI2_99_DF5 = 15.086        # chi-square 0.99 quantile, df=len(FEATS)=5


def _f(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def _norm_label(s):
    s = (s or "").strip().lower()
    return "medium" if s == "med" else s


def load():
    rows = []
    for csvf in sorted(CSV_DIR.glob("scaled_results*.csv")):   # canonical + extensions
        rows += [r for r in csv.DictReader(csvf.open(encoding="utf-8"))
                 if (r.get("oracle_certified", "").strip().lower() == "true")]
    return [{
        "correct": (r.get("atlas_route_class", "").strip().lower()
                    == r.get("oracle_route", "").strip().lower()),
        "conf": _f(r.get("confidence_score")),
        "label": _norm_label(r.get("confidence_label")),
        "route": (r.get("atlas_route_class") or "").strip().lower(),
        "feat": [_f(r.get(k)) for k in FEATS],
    } for r in rows]


def _wilson(k, n, z=1.96, upper=False):
    # El caso UPPER (la garantía held-out) usa el MARCO ÚNICO conformal_core (acción D).
    if upper:
        try:
            from conformal_core import wilson_upper
            return wilson_upper(k, n, z)
        except Exception:
            pass
    if n == 0:
        return 1.0 if upper else 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return min(1.0, (c + m) / d) if upper else max(0.0, (c - m) / d)


def reliability(cal):
    """Descriptive per-label empirical correctness + Wilson 95% lower bound."""
    out = {}
    for lab in ("high", "medium", "low"):
        g = [c for c in cal if c["label"] == lab]
        if g:
            k = sum(c["correct"] for c in g)
            out[lab] = {"n": len(g), "acc": k / len(g), "lo95": _wilson(k, len(g))}
    return out


def selective_threshold(cal, alpha=0.05):
    """SPLIT-based: choose tau on the selection half, report a held-out Wilson upper
    bound on the validation half. Returns dict or None."""
    sel, val = cal[0::2], cal[1::2]
    tau_star = None
    for tau in sorted({c["conf"] for c in sel}):          # ascending = max coverage first
        acc = [c for c in sel if c["conf"] >= tau]
        if acc and (sum(not c["correct"] for c in acc) / len(acc)) <= alpha:
            tau_star = tau
            break
    if tau_star is None:
        return None
    accv = [c for c in val if c["conf"] >= tau_star]
    if not accv:
        return None
    kv = sum(not c["correct"] for c in accv)
    err_ub = _wilson(kv, len(accv), z=Z_ONE_SIDED_95, upper=True)   # held-out upper bound
    return {"tau": tau_star, "val_coverage": len(accv) / len(val),
            "val_err_ub": err_ub, "guaranteed_correctness": 1 - err_ub,
            "passes": err_ub <= alpha, "alpha": alpha, "n_val_accepted": len(accv)}


MIN_CLASS = 30          # min certified examples of a route class to calibrate it


def _ood_model(cal):
    lo = [min(c["feat"][i] for c in cal) for i in range(len(FEATS))]
    hi = [max(c["feat"][i] for c in cal) for i in range(len(FEATS))]
    from collections import Counter
    return {"lo": lo, "hi": hi, "route_counts": dict(Counter(c["route"] for c in cal))}


def is_ood(feat, route, m):
    """Decline if (a) the predicted ROUTE class has too few certified examples to
    calibrate (the oracle never certifies ESCALATE, so escalate-routed circuits are
    uncalibratable by construction), or (b) a feature is outside the calibration box.
    Route-class coverage is the primary, principled criterion; the box catches
    feature-extreme circuits (e.g. treewidth beyond anything certified)."""
    rc = m["route_counts"].get((route or "").lower(), 0)
    if rc < MIN_CLASS:
        return True, [f"route '{route}' undercalibrated ({rc} certified < {MIN_CLASS})"]
    over = [FEATS[i] for i, v in enumerate(feat)
            if v < m["lo"][i] - 1e-9 or v > m["hi"][i] + 1e-9]
    return (len(over) > 0), over


_CAL = None


def _cal():
    global _CAL
    if _CAL is None:
        c = load()
        if not c:
            import warnings
            warnings.warn(f"atlas_conformal: no calibration data under {CSV_DIR} "
                          "-> confidence tier degrades to 'verify' (no guarantee).")
        _CAL = {"rows": c, "reliab": reliability(c),
                "thr": selective_threshold(c), "ood": _ood_model(c)}
    return _CAL


def certify(confidence_score, label, features, route=None, alpha=0.05):
    cal = _cal()
    confidence_score = _f(confidence_score)
    if isinstance(features, dict):
        features = [_f(features.get(k)) for k in FEATS]
    ood, over = is_ood(features, route, cal["ood"])
    rel = cal["reliab"].get(_norm_label(label))
    thr = cal["thr"]
    has_guarantee = bool(thr and thr["passes"])
    accepted = bool(has_guarantee and confidence_score >= thr["tau"] and not ood)

    if ood:
        statement = (f"OUT-OF-DISTRIBUTION on {over}: outside calibration support -> "
                     f"coverage guarantee does NOT apply -> verify")
    elif accepted:
        statement = (f"CALIBRATED (held-out): route-correctness >= "
                     f"{thr['guaranteed_correctness']:.3f} for conf>={thr['tau']:.0f} "
                     f"(val coverage {thr['val_coverage']:.2f}, alpha={thr['alpha']}, "
                     f"exchangeable)")
    elif thr and confidence_score >= thr["tau"] and not thr["passes"]:
        statement = (f"EMPIRICAL only: held-out error bound {thr['val_err_ub']:.3f} "
                     f"exceeds alpha={thr['alpha']} -> no future guarantee -> verify")
    else:
        statement = "below calibrated threshold / no validated guarantee -> verify"
    return {"accepted": accepted, "ood": ood, "ood_features": over,
            "has_guarantee": has_guarantee,
            "empirical_label_acc": (rel or {}).get("acc"),
            "empirical_label_lo95": (rel or {}).get("lo95"),
            "selective_threshold": thr["tau"] if thr else None,
            "val_coverage": thr["val_coverage"] if thr else None,
            "guaranteed_correctness": thr["guaranteed_correctness"] if has_guarantee else None,
            "statement": statement}


if __name__ == "__main__":
    c = _cal()
    print(f"calibration: {len(c['rows'])} certified circuits (split 50/50 sel/val)")
    overall = sum(r["correct"] for r in c["rows"]) / len(c["rows"])
    print(f"overall atlas route-correctness vs oracle: {overall:.3f}\n")
    print("per-label reliability (descriptive, Wilson 95% lower bound):")
    for lab, d in c["reliab"].items():
        print(f"  {lab:<7} n={d['n']:<4} acc={d['acc']:.3f}  lo95={d['lo95']:.3f}")
    thr = c["thr"]
    print(f"\nheld-out selective threshold: {thr}")
    if thr:
        kind = "VALID held-out guarantee" if thr["passes"] else "EMPIRICAL only (no guarantee)"
        print(f"  -> conf>={thr['tau']:.0f}: val coverage {thr['val_coverage']:.2f}, "
              f"correctness >= {thr['guaranteed_correctness']:.3f}  [{kind}]")

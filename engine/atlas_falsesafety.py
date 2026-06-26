#!/usr/bin/env python3
"""atlas_falsesafety — a false-safety RISK signal INDEPENDENT of the predicted route.

The conformal OOD decline keys off the PREDICTED route (declines when Atlas itself
says hpc/escalate). A false-safety is precisely when Atlas does NOT route hard, so
that defense is blind to it by construction. This module supplies the missing,
route-independent signal: it asks "how fragile is the cheap-looking verdict?",
using evidence the adjudicator already exposes:

  S1 route_spread   — among the VALID estimators (route_adjudication.valid_routes),
                      do they span more than one route class? If a trusted estimator
                      (e.g. exact statevector) routes HARDER than the chosen route,
                      the cheap verdict rests on a different estimator being cheaper.
                      (This is exactly the n=28 ladder false-safety: statevector->HPC
                      is in valid_routes but treewidth->TENSOR was chosen.)
  S2 threshold_margin — how close the governing cost sits to the next HARDER threshold
                      in its own estimator's table. A small margin = a small
                      measurement/threshold error flips the route to harder = fragile.
  S3 invalidated    — the cheap verdict coexists with an invalidated estimator
                      (e.g. truncated MPS that could not certify) => reliance on a
                      non-exact bound.

risk in [0,1]; band LOW/ELEVATED/HIGH. NONE of these use the chosen route as the
discriminator — they measure the evidence's fragility, so they fire even when Atlas
confidently routes cheap. This is the signal the predicted-route-keyed decline lacks.
"""
from __future__ import annotations

# Per-estimator route thresholds (kept in lockstep with route_adjudicator.py).
ORDER = {"cpu": 0, "tensor": 1, "hpc_first": 2, "escalate": 3}
TW = [("cpu", 24.0), ("tensor", 29.0), ("hpc_first", 40.0)]          # by log2 contraction width
MPS = [("cpu", 5.5), ("tensor", 10.0), ("hpc_first", 14.5)]          # by log2 bond
SV = [("cpu", 21), ("tensor", 27), ("hpc_first", 33)]                # by qubit count n
_TABLE = {"treewidth": TW, "contraction(treewidth)": TW, "mps": MPS,
          "mps(entangle)": MPS, "statevector": SV}


def _next_harder_threshold(estimator, cost):
    """Margin (in the estimator's own units) from `cost` up to the next HARDER route
    boundary. Small margin => fragile. None if no table / no harder boundary."""
    tbl = _TABLE.get((estimator or "").lower())
    if tbl is None or cost is None:
        return None
    for _route, thr in tbl:
        if cost <= thr:
            return thr - cost          # distance up to this boundary's ceiling
    return 0.0                          # already past the hardest tabled boundary


def false_safety_risk(adjudication: dict, exact_ctx: dict | None = None) -> dict:
    """Compute the route-independent false-safety risk from cost_atlas's
    route_adjudication dict. Returns {risk, band, signals, reads}.

    exact_ctx (optional, from the cost_atlas result): {stim_clifford, treewidth_exact,
    mps_truncated}. CRITICAL: if the GOVERNING (cheapest-valid) estimator is EXACT/
    trustworthy, the cheap verdict is certified and the risk is LOW even though a
    pessimistic-by-construction estimator (e.g. statevector-by-qubit-count) routes
    harder. Without this gate the signal over-fires (~70% of trivial cpu circuits),
    because statevector-by-n is harder than the chosen route for almost any n>21.
    Risk fires only when the cheap verdict rests on a NON-exact bound."""
    ra = adjudication or {}
    ex = exact_ctx or {}
    chosen = (ra.get("route") or "").lower()
    chosen_ord = ORDER.get(chosen, 0)
    gcost = ra.get("governing_cost_log2")
    gest = ra.get("governing_estimator")

    # S1: do any VALID estimators route harder than the chosen route?
    valid = ra.get("valid_routes") or []
    harder = []
    max_ord = chosen_ord
    for v in valid:
        o = ORDER.get((v.get("route") or "").lower(), 0)
        max_ord = max(max_ord, o)
        if o > chosen_ord:
            harder.append({"estimator": v.get("estimator"), "route": v.get("route"),
                           "cost_log2": v.get("cost_log2")})
    spread = max_ord - chosen_ord                       # >=1 means a valid estimator disagrees harder
    s1 = min(1.0, spread / 2.0)

    # S2: margin from the governing cost to the next harder threshold (fragility).
    margin = _next_harder_threshold(gest, gcost)
    s2 = 0.0 if margin is None else max(0.0, 1.0 - margin / 4.0)   # <4 log2 of slack ramps risk

    # S3: a cheap-side verdict resting on an invalidated estimator (e.g. truncated MPS).
    inval = ra.get("invalidated_estimators") or []
    s3 = 0.6 if (inval and chosen in ("cpu", "tensor")) else 0.0

    # GATE: if the governing (cheapest-valid) estimator is EXACT, the cheap verdict is
    # certified -> suppress S1/S2 (a pessimistic statevector-by-n disagreement is NOT a
    # real risk when an exact method certifies the cheap route). Only non-exact governing
    # (greedy treewidth / truncated MPS) leaves a genuine false-safety opening.
    g = (gest or "").lower()
    governing_exact = (
        bool(ex.get("stim_clifford")) or
        ("treewidth" in g and bool(ex.get("treewidth_exact"))) or
        ("mps" in g and not ex.get("mps_truncated", True)) or
        ("statevector" in g) or ("spread" in g) or ("stim" in g) or ("magic" in g))
    if governing_exact:
        s1 = 0.0
        s2 = 0.0
        s3 = 0.0

    risk = max(s1, s2, s3)              # worst signal dominates (any one fragility is enough)
    band = "HIGH" if risk >= 0.66 else "ELEVATED" if risk >= 0.33 else "LOW"
    reads = []
    if harder:
        reads.append("a trusted estimator routes HARDER than the chosen route "
                     f"({'; '.join(h['estimator'] + '->' + str(h['route']) for h in harder)}) "
                     "-> the cheap verdict rests on a cheaper estimator being correct")
    if margin is not None and margin < 4.0:
        reads.append(f"governing cost is only {margin:.1f} (log2) below the next HARDER "
                     f"threshold for {gest} -> route is boundary-fragile")
    if s3:
        reads.append("cheap verdict coexists with an invalidated (truncated/non-exact) "
                     "estimator -> reliance on a non-certified bound")
    if not reads:
        reads.append("no route-independent fragility detected")
    return {"risk": round(risk, 3), "band": band,
            "signals": {"route_spread": spread, "harder_estimators": harder,
                        "threshold_margin_log2": margin, "invalidated_present": bool(inval)},
            "reads": "; ".join(reads),
            "note": "INDEPENDENT of the predicted route: measures evidence fragility, so "
                    "it fires even when Atlas confidently routes cheap (the blind spot of "
                    "the predicted-route-keyed conformal decline)."}


if __name__ == "__main__":
    import os, sys, json
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
    sys.path.insert(0, os.path.dirname(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "benchmarks"))
    from atlas import cost_atlas, safe_parse
    import build_calibration_corpus as B
    cases = [("ladder", 28, 8, 3, "the known false-safety"),
             ("line", 10, 8, 1, "trivial cpu"),
             ("expander", 40, 50, 1, "genuinely hard")]
    for topo, n, t, s, why in cases:
        q = B.build(topo, n, t, s); pn, c, _ = safe_parse(q)
        r = cost_atlas(pn, c); ra = r.get("route_adjudication") or {}
        fr = false_safety_risk(ra, {"stim_clifford": r.get("stim_clifford"),
                                    "treewidth_exact": r.get("treewidth_exact"),
                                    "mps_truncated": r.get("mps_truncated")})
        print(f"\n{topo} n={n} ({why}): route={ra.get('route')} -> FS-risk {fr['risk']} [{fr['band']}]")
        print("  ", fr["reads"][:140])

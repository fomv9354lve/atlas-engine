"""Operational route adjudication for Atlas.

This module is deliberately backend-side: it decides compute routes from
measured diagnostics and estimator validity, not from UI labels. Its purpose is
to make Atlas more than "treewidth with a dashboard":

* exact/non-truncated MPS can override a high treewidth false alarm;
* truncated MPS is treated as a lower bound and cannot certify safety;
* treewidth is used as the governing fallback only when cheaper routes are not
  valid;
* single-estimator counterfactuals are emitted for falsification.
"""
from __future__ import annotations

# Route thresholds calibrated to real wall-clock on the local machine via
# benchmarks/calibrate_thresholds.py (see benchmarks/threshold_calibration.md).
# MPS bounds come from a clean bond^3 timing fit (CPU<1s at log2-bond ~5.6);
# treewidth CPU bound is measured (<1s up to width ~24) and the TENSOR bound is
# the single-node memory limit (2^29 * 16B = 8 GB) because high-width contraction
# timings are overhead-dominated and extrapolate unreliably. Rerun the calibrator
# on the deployment hardware to re-tie these to that machine.
CPU_SPREAD_MAX = 1.0
CPU_MPS_MAX = 5.5        # was 2.0 (bond 4) -- far too conservative; a bond-48 MPS finishes <1s
TENSOR_MPS_MAX = 10.0    # ~bond 1024, ~60s
HPC_MPS_MAX = 14.5       # was inline 20; ~1h budget
CPU_TW_MAX = 24.0        # was 12.0; width-24 contraction measured <1s
TENSOR_TW_MAX = 29.0     # was 24.0; 2^29*16B = 8 GB single-node memory limit
HPC_TW_MAX = 40.0        # terabyte-scale, cluster

# Full statevector is an EXACT, always-available classical route whose only cost
# is 2^n memory/time. Ignoring it made Atlas (and the oracle) over-escalate small
# and medium circuits that a laptop simulates outright, regardless of treewidth /
# MPS / magic. Thresholds from benchmarks/calibrate_thresholds.py (CPU n<=20.9,
# TENSOR n<=27.1, HPC n<=33.3 on this machine).
SV_CPU_MAX_N = 21        # 2^21 state ~ 32 MB, < 1 s
SV_TENSOR_MAX_N = 27     # 2^27 ~ 2 GB
SV_HPC_MAX_N = 33        # 2^33 ~ 128 GB; beyond this, no classical statevector

ORDER = {"CPU": 0, "TENSOR": 1, "HPC_FIRST": 2, "ESCALATE": 3}


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _numornone(x):
    return x if isinstance(x, (int, float)) else None


def _costs(result: dict) -> dict:
    c = result.get("costs_log2") or {}
    # mps/treewidth pueden ser None si el estimador ABSTUVO (excedio su presupuesto wall-clock). Antes se
    # forzaban a 0.0 (_num) -> un fold no-computado parecia 2^0 (baratisimo) -> ruta CPU falsa. Ahora None:
    # el adjudicador lo trata como "no computado" (invalida la ruta), no como coste cero.
    return {
        "magic": _num(c.get("fold(magic)")),
        "spread": c.get("spread(local)") if isinstance(c.get("spread(local)"), (int, float)) else None,
        "mps": _numornone(c.get("MPS(entangle)")),
        "treewidth": _numornone(c.get("contraction(treewidth)")),
    }


def treewidth_only_route(result: dict) -> str:
    tw = _costs(result)["treewidth"]
    if tw is None:                       # abstuvo -> sin ruta certificada por treewidth
        return "ESCALATE"
    if tw <= CPU_TW_MAX:
        return "CPU"
    if tw <= TENSOR_TW_MAX:
        return "TENSOR"
    if tw <= HPC_TW_MAX:
        return "HPC_FIRST"
    return "ESCALATE"


def mps_only_route(result: dict) -> str:
    mps = _costs(result)["mps"]
    if mps is None:                      # abstuvo -> sin ruta certificada por MPS
        return "ESCALATE"
    if mps <= CPU_MPS_MAX:
        return "CPU"
    if mps <= TENSOR_MPS_MAX:
        return "TENSOR"
    if mps <= HPC_MPS_MAX:
        return "HPC_FIRST"
    return "ESCALATE"


def magic_only_route(result: dict) -> str:
    t = int(result.get("t_count") or 0)
    if t == 0:
        return "CPU"
    if t <= 24:
        return "TENSOR"
    if t <= 96:
        return "HPC_FIRST"
    return "ESCALATE"


def _confidence(route: str, governing: dict, valid_routes: list[dict], invalidated: list[dict], result: dict) -> dict:
    """Confidence that the governing route is the *right* operational call.

    Calibration note (handoff 16C): an earlier version rewarded the raw *count*
    of valid routes. That is backwards -- when estimators disagree about the
    route, the decision is less certain, not more. Empirically (scaled benchmark)
    that inverted the reliability curve: high-confidence circuits were the very
    over-escalation cases where treewidth contradicted a cheap exact MPS. We now
    reward *corroboration* of the chosen route and penalise *disagreement* in the
    route order across estimators.
    """
    methods = ((result.get("ground_truth") or {}).get("methods") or {})
    coverage = sum(1 for v in methods.values() if v) / max(1, len(methods))
    exact_mps = not bool(result.get("mps_truncated"))
    tw_exact = bool(result.get("treewidth_exact"))
    spread_known = _costs(result)["spread"] is not None
    support = 0.30 + 0.18 * coverage + 0.12 * tw_exact + 0.10 * spread_known

    # Exact MPS only *supports* confidence when the chosen route does not undercut
    # it. If a heuristic (e.g. bounded Pauli spread) routed cheaper than the exact
    # MPS bond demands, we have overridden a measurement with a guess -> lower
    # confidence, not higher. (We do not re-route here: the MPS CPU/TENSOR
    # threshold itself is a fixed cost-model constant pending wall-clock
    # calibration; we only refuse to claim confidence we have not earned.)
    if exact_mps:
        mps_demands = ORDER[mps_only_route(result)]
        if ORDER[route] >= mps_demands:
            support += 0.18                                                 # exact MPS agrees with the route
        else:
            support -= 0.15                                                 # heuristic undercut an exact measurement
            exact_mps = False                                               # not an exact basis for the chosen route

    orders = [ORDER[r["route"]] for r in valid_routes]
    disagreement = (max(orders) - min(orders)) if orders else 0          # 0..3 route-classes apart
    corroboration = sum(1 for o in orders if o == ORDER[route])          # estimators backing the chosen route
    # An *exact* governing certificate (Clifford via Stim, exact non-truncated
    # MPS, or exact treewidth) is proof, not a guess: heuristic estimators
    # disagreeing with it is irrelevant, so we do not penalise disagreement and
    # add a certainty bonus. Only heuristic-governed routes pay the disagreement
    # penalty. This keeps large Clifford circuits (over-escalation fix) at high
    # confidence instead of being dragged down by a spurious treewidth.
    est = governing.get("estimator")
    exact_basis = (est == "Stim stabilizer"
                   or est == "statevector"
                   or (est == "MPS" and not bool(result.get("mps_truncated")))
                   or (est == "treewidth" and bool(result.get("treewidth_exact"))))
    support += min(0.10, 0.05 * (corroboration - 1))                     # independent estimators agreeing
    if exact_basis:
        support += 0.12                                                  # exact certificate: we have proof
    else:
        support -= min(0.24, 0.08 * disagreement)                       # heuristic-governed: penalise conflict
    support -= min(0.22, 0.06 * len(invalidated))
    if route == "HPC_FIRST":
        support -= 0.05

    score = max(0, min(100, round(100 * support)))
    label = "high" if score >= 75 else "medium" if score >= 45 else "low"
    return {"score": score, "label": label, "formula": {
        "method_coverage": round(coverage, 3),
        "exact_mps": exact_mps,
        "treewidth_exact": tw_exact,
        "spread_known": spread_known,
        "route_corroboration": corroboration,
        "route_disagreement": disagreement,
        "invalidated_estimator_count": len(invalidated),
    }}


def adjudicate_route(result: dict, budget_log2: float = HPC_TW_MAX, n: int | None = None) -> dict:
    c = _costs(result)
    mps_truncated = bool(result.get("mps_truncated"))
    valid_routes: list[dict] = []
    invalidated: list[dict] = []

    # Statevector certificate: exact and always valid up to the memory wall.
    nn = int(n if n is not None else (result.get("n") or 0))
    if 0 < nn <= SV_HPC_MAX_N:
        svr = "CPU" if nn <= SV_CPU_MAX_N else "TENSOR" if nn <= SV_TENSOR_MAX_N else "HPC_FIRST"
        valid_routes.append({"route": svr, "estimator": "statevector", "cost_log2": float(nn),
                             "reason": f"full statevector ({nn} qubits) fits the measured classical budget"})

    # Clifford circuits are simulated in polynomial time by Stim for *any* n,
    # regardless of treewidth or MPS bond. Without this certificate the
    # adjudicator over-escalates large Clifford circuits whose greedy treewidth
    # looks expensive (handoff 16A over-escalation). Gated on Stim-confirmed
    # Clifford (not just t_count==0), so non-Clifford rz circuits are not
    # wrongly certified.
    if bool(result.get("stim_clifford")):
        valid_routes.append({"route": "CPU", "estimator": "Stim stabilizer", "cost_log2": 0.0,
                             "reason": "Clifford circuit: Stim simulates in polynomial time for any n"})

    spread = c["spread"]
    if spread is not None and spread <= CPU_SPREAD_MAX:
        valid_routes.append({"route": "CPU", "estimator": "Pauli spread", "cost_log2": round(spread, 2),
                             "reason": "local Pauli spread remains bounded"})

    if c["mps"] is not None and not mps_truncated:
        if c["mps"] <= CPU_MPS_MAX:
            valid_routes.append({"route": "CPU", "estimator": "MPS", "cost_log2": round(c["mps"], 2),
                                 "reason": "exact MPS bond is in a laptop range"})
        elif c["mps"] <= TENSOR_MPS_MAX:
            valid_routes.append({"route": "TENSOR", "estimator": "MPS", "cost_log2": round(c["mps"], 2),
                                 "reason": "exact MPS bond is in tensor-network range"})
        else:
            valid_routes.append({"route": "HPC_FIRST", "estimator": "MPS", "cost_log2": round(c["mps"], 2),
                                 "reason": "exact MPS bond exceeds ordinary tensor budget"})
    elif c["mps"] is None:                       # MPS abstuvo (excedio su presupuesto) -> no computado
        invalidated.append({"estimator": "MPS", "observed": "not computed (per-estimator budget exceeded)",
                            "reason": "MPS build exceeded its wall-clock budget and abstained; cannot certify a route"})
    else:
        invalidated.append({"estimator": "MPS", "observed": f">=2^{round(c['mps'], 2)}",
                            "reason": "truncated MPS is a lower bound and cannot certify a cheap route"})

    if c["treewidth"] is None:                   # treewidth abstuvo (cotengra excedio su presupuesto) -> no computado
        invalidated.append({"estimator": "treewidth", "observed": "not computed (per-estimator budget exceeded)",
                            "reason": "contraction-path search exceeded its wall-clock budget and abstained"})
    elif c["treewidth"] <= CPU_TW_MAX:
        valid_routes.append({"route": "CPU", "estimator": "treewidth", "cost_log2": round(c["treewidth"], 2),
                             "reason": "contraction width is tiny"})
    elif c["treewidth"] <= TENSOR_TW_MAX:
        valid_routes.append({"route": "TENSOR", "estimator": "treewidth", "cost_log2": round(c["treewidth"], 2),
                             "reason": "contraction width is within tensor-network budget"})
    elif c["treewidth"] <= budget_log2:
        valid_routes.append({"route": "HPC_FIRST", "estimator": "treewidth", "cost_log2": round(c["treewidth"], 2),
                             "reason": "contraction width requires HPC review"})
    else:
        valid_routes.append({"route": "ESCALATE", "estimator": "treewidth", "cost_log2": round(c["treewidth"], 2),
                             "reason": "contraction width exceeds declared classical budget"})

    if not valid_routes:
        # TODOS los estimadores abstuvieron y no hay certificado de statevector factible (n grande): deferral
        # operacional HONESTO (no es una afirmacion de dureza), en vez de un cuelgue crudo. Es el "partial
        # graceful" para los circuitos genuinamente enormes cuyos folds exceden su presupuesto.
        valid_routes.append({"route": "ESCALATE", "estimator": "compute-bound", "cost_log2": None,
                             "reason": "all estimators exceeded their per-estimator wall-clock budget and no "
                                       "statevector certificate is available; defer to HPC / longer budget"})

    governing = min(valid_routes, key=lambda r: (ORDER[r["route"]],
                                                 r["cost_log2"] if r["cost_log2"] is not None else 1e9))
    route = governing["route"]
    baselines = {
        "treewidth_only": treewidth_only_route(result),
        "mps_only": mps_only_route(result),
        "magic_only": magic_only_route(result),
    }
    disagreements = {k: v for k, v in baselines.items() if v != route}
    counterfactuals = []
    if baselines["treewidth_only"] in ("HPC_FIRST", "ESCALATE") and route in ("CPU", "TENSOR"):
        counterfactuals.append({"baseline": "treewidth_only", "failure_mode": "false_alarm",
                                "why_atlas_differs": "a cheaper exact route was found before escalating"})
    if mps_truncated and baselines["mps_only"] in ("CPU", "TENSOR") and route in ("HPC_FIRST", "ESCALATE"):
        counterfactuals.append({"baseline": "mps_only", "failure_mode": "false_safety",
                                "why_atlas_differs": "truncated MPS lower bound cannot certify tractability"})
    if baselines["magic_only"] != route:
        counterfactuals.append({"baseline": "magic_only", "failure_mode": "missing_structure",
                                "why_atlas_differs": "T-count alone ignores entanglement and contraction structure"})

    conf = _confidence(route, governing, valid_routes, invalidated, result)
    return {
        "route": route,
        "route_order": ORDER[route],
        "governing_estimator": governing["estimator"],
        "governing_cost_log2": governing["cost_log2"],
        "governing_reason": governing["reason"],
        "valid_routes": valid_routes,
        "invalidated_estimators": invalidated,
        "single_estimator_baselines": baselines,
        "baseline_disagreements": disagreements,
        "counterfactuals": counterfactuals,
        "confidence": conf,
        "causal_chain": [
            {"step": "measure", "statement": "compute Pauli spread, MPS, treewidth and magic proxies"},
            {"step": "validate", "statement": "discard estimator outputs that are lower bounds only"},
            {"step": "select", "statement": f"choose cheapest valid route: {route} via {governing['estimator']}"},
        ],
    }

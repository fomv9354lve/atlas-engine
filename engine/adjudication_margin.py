"""adjudication_margin — theorem-grounded margin & tail annotations for Atlas.

Every Atlas route decision compares a measured cost c (log2 units) against fixed
thresholds t (route_adjudicator constants). This module makes the DISTANCE to the
nearest decision boundary a first-class output, and attaches the PROVEN functional
form of the misroute-risk / confidence-tail bounds from the operator's Walsh /
inverse-Ginibre program — with the honest layering:

    the FORM of each bound is proven (QED in that program);
    the Atlas-specific CONSTANTS are NOT yet calibrated / are empirical.

So this module never emits a numeric probability. It emits margins (measured) and
bound FORMS (proven), each labeled as such.

Grounding (operator's notes, read-only):

* threshold-passage / sign-tanh envelope
  (notes/threshold_passage_from_anticoncentration_qed.md): the deterministic
  two-term envelope, for every smoothing scale a > 0,

      |sign(t) - tanh(beta t)| <= 2*1{|t| <= a} + 2*exp(-2*beta*a),

  combined with a small-ball (anticoncentration) constant C such that
  P(|t| <= a) <= C*a, gives after optimizing a ~ beta^(-1/2):

      E|sign - tanh_beta| <= 2*C*beta^(-1/2) + 2*exp(-2*sqrt(beta)).

  Transported to route adjudication (a hard threshold decision sign(c - t) vs any
  smoothed/perturbed version of it), this is the two-term misroute-risk envelope:

      P(misroute under perturbation scale a) <= P(|c - t| <= a) + exp-tail(a).

  The small-ball constant for Atlas's cost distribution is NOT measured yet, so
  only the margin |c - t| (measured) and the bound FORM (proven) are emitted.

* denominator cavity-shield (notes/denominator_cavity_shield_qed.md):
  deterministic Z >= Z_ab, hence |N/Z| <= |N/Z_ab| — ratio-type quantities are
  shielded against denominator collapse by a deterministic inequality, not a
  probabilistic assumption.

* weighted-chi^2 all-order inverse moments
  (notes/haar_frame_denominator_control.md, lemma (1.1), via
  notes/weighted_chisquare_local_density_ratio_qed.md): for weighted chi-square
  denominators with bounded infinitesimal weights, E[((1/m)/a)^p] <= C_{p,C} for
  EVERY fixed p — all polynomial-order inverse moments are finite, i.e. the
  lower tail of the denominator is smaller than every polynomial order
  (P(sum_i w_i Z_i^2 <= u) <= C_q * u^q for every fixed q). This pins the
  FUNCTIONAL FORM of the tails of ratio-type confidence quantities:
  sub-Weibull-type upper tails with all-order inverse-moment control on the
  denominator side.

This module is ANNOTATION-ONLY: it never changes a route, a confidence score,
or a tier. All outputs are additive fields.
"""
from __future__ import annotations

# Estimators whose route is granted by a theorem / exact certificate rather than
# by comparing a scalar cost against a threshold — there is no decision boundary
# to have a margin against.
_THEOREM_GATED = ("stim", "clifford")
# The all-abstained deferral pseudo-estimator (route_adjudicator emits it when
# every estimator exceeded its wall-clock budget).
_NO_COST = ("compute-bound",)

# The two-term misroute-risk envelope, stated ONCE, honestly. Constants are
# deliberately symbolic: the small-ball constant C for Atlas's cost distribution
# and the smoothing sharpness beta are NOT calibrated for Atlas yet.
RISK_FORM = (
    "P(misroute) <= P(|c - t| <= a) + 2*exp(-2*beta*a) for every smoothing scale "
    "a > 0 (sign/tanh threshold-passage envelope); with a small-ball constant C "
    "(P(|c - t| <= a) <= C*a) the optimal a ~ beta^(-1/2) gives "
    "P(misroute) <= 2*C*beta^(-1/2) + 2*exp(-2*sqrt(beta)). "
    "Form proven in the Walsh program; Atlas-specific constants (small-ball C of "
    "the cost distribution, beta) uncalibrated — no numeric probability claimed."
)

# ONE-SIDED risk (ties the margin to the soundness guarantee, route_adjudicator.soundness):
# a CHEAP-certifying estimator is EXACT or an UPPER BOUND, so a misroute at a boundary can only
# make the route MORE conservative than truth (over-escalation), NEVER less (false-cheap). Hence the
# envelope above bounds ONLY the over-provisioning direction; the false-safety direction is 0 by
# construction, not by the (uncalibrated) constant. This is the honest closure of "what does the
# margin's risk mean" — its risk is one-sided, and the safe side needs no constant at all.
RISK_DIRECTION = (
    "one-sided: bounds OVER-escalation only (routing costlier than truth). The false-cheap direction "
    "is structurally impossible (cheap routes are exact/upper-bound — see route_adjudication.soundness), "
    "so it carries ZERO risk independent of the uncalibrated small-ball constant."
)


def boundary_margin(estimator: str, cost_log2, boundaries) -> dict:
    """Boundary-margin block for the GOVERNING estimator of a route decision.

    estimator   -- governing estimator name (e.g. "MPS", "treewidth",
                   "statevector", "Pauli spread", "Stim stabilizer").
    cost_log2   -- the governing cost c in log2 units (None if not cost-based).
    boundaries  -- list of (threshold_log2, separates) route boundaries for THIS
                   estimator, e.g. [(5.5, "CPU|TENSOR"), (10.0, "TENSOR|HPC_FIRST")].
                   Threshold constants live in route_adjudicator (single source of
                   truth); this function only measures distances against them.

    Returns {distance_log2, nearest_boundary, governing, risk_form} — the margin
    is MEASURED; the risk bound is a proven FORM with uncalibrated Atlas constants
    (see RISK_FORM). Never a numeric probability.
    """
    est_l = (estimator or "").lower()
    base = {"governing": estimator, "units": "log2(cost)", "risk_form": RISK_FORM}
    if any(k in est_l for k in _THEOREM_GATED):
        return {**base, "distance_log2": None, "nearest_boundary": None,
                "note": "theorem-gated route (exact certificate, e.g. Gottesman-Knill): "
                        "not a threshold decision, so no boundary margin applies"}
    if cost_log2 is None or any(k in est_l for k in _NO_COST) or not boundaries:
        return {**base, "distance_log2": None, "nearest_boundary": None,
                "note": "no scalar cost / no threshold table for this estimator; "
                        "margin undefined"}
    c = float(cost_log2)
    t, sep = min(boundaries, key=lambda b: abs(c - float(b[0])))
    return {**base, "risk_direction": RISK_DIRECTION,
            "distance_log2": round(abs(c - float(t)), 3),
            "nearest_boundary": {"threshold_log2": float(t), "separates": sep},
            "cost_log2": round(c, 3)}


def tail_form() -> dict:
    """Feature-2 annotation for the (isotonic-calibrated, empirical) confidence
    block: the PROVEN functional FORM of the tails of ratio-type confidence
    quantities, per the operator's QED lemmas. Additive only — the confidence
    score computation itself is untouched."""
    return {
        "form": "sub-Weibull/χ² inverse-moment (form QED in inverse-Ginibre program)",
        "status": "form proven, Atlas constants empirical (isotonic)",
        "applies_to": "ratio-type confidence quantities (corroboration ratios, "
                      "calibrated score); annotation only — score computation unchanged",
        "lemmas": [
            "deterministic denominator cavity-shield: Z >= Z_ab, hence "
            "|N/Z| <= |N/Z_ab| — denominator collapse excluded deterministically "
            "(denominator_cavity_shield_qed)",
            "weighted-χ² all-order inverse moments: E[((1/m)/a)^p] <= C_{p,C} for "
            "every fixed p (equivalently lower tail P(Q <= u) <= C_q*u^q for every "
            "fixed q) — ratio tails controlled at all polynomial orders "
            "(haar_frame_denominator_control (1.1) + "
            "weighted_chisquare_local_density_ratio_qed)",
        ],
        "honest_layering": "form: theirs + proven (Walsh/inverse-Ginibre program); "
                           "constants: ours + measured (isotonic calibration on the "
                           "Atlas benchmark corpus)",
    }

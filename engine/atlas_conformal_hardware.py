#!/usr/bin/env python3
"""atlas_conformal_hardware — corrección APRENDIDA + conformal del sesgo de inferencia hardware.

HALLAZGO (auto-corrección #10, datos PROPIOS en metal real ibm_kingston, 2026-06-22): la
inferencia de fidelidad de primer orden F = Π(1-e_gate) SOBREESTIMA la fidelidad real a
profundidad. En 9 circuitos 2D-random (Porter-Thomas, n=12) corridos en ibm_kingston, la XEB
medida cae MUCHO más rápido que la inferida: a d=12, F_inf=0.77 vs F_meas=0.40. El error real
por capa es ~2.6× el inferido (κ̂≈2.6, NO κ<1).

REVERSIÓN del signo: la tabla anterior (cross-session, device-faithful Aer) daba κ̂≈0.40 (<1,
"el hardware es mejor que lo inferido, extiende el techo"). Eso era ARTEFACTO DEL SIMULADOR: Aer
subestima el ruido CORRELACIONADO/no-Markoviano (crosstalk, TLS, leakage) que el metal real sí
tiene. En metal real κ̂>1 → la corrección APRIETA el techo de profundidad (seguridad), no lo
extiende. El κ=1 "conservador" ya era OPTIMISTA en hardware.

Fix (mismo patrón de dos niveles que el resto del motor):
  1. modelo físico: e_real ≈ κ̂·e_inf (κ̂>1 = penalización por ruido correlacionado real), aprendido.
  2. conformal: banda con cobertura, vía residuos leave-one-out (honesta con n pequeño).

ALCANCE HONESTO: 9 puntos PROPIOS en ibm_kingston, familia 2D-random Porter-Thomas a n=12, 2048
shots c/u (11 jobs, incl. d=11/d=13). 9 son PT-válidos (colisión≈2; d=2,4 anti-concentrados → se
filtran del κ̂) → cobertura conformal 90% (n/(n+1)=9/10).
Es una corrección de PRIMER ORDEN sobre datos escasos → el VALOR es la banda + el SIGNO, no el
punto. Cada circuito tiene su propio layout físico → varianza de embedding incluida.
"""
from __future__ import annotations
import math

# (depth, XEB_inferida, XEB_medida, colisión) — DATOS PROPIOS, ibm_kingston, 2D-random PT, n=12,
# 2048 shots. F_inf = 1er orden desde medianas MEDIDAS; F_meas = linear-XEB norm. por colisión real.
CALIB_RAW = [(2, 0.884, 0.965, 36.0), (4, 0.858, 0.854, 6.0), (6, 0.836, 0.780, 1.37),
             (8, 0.813, 0.575, 1.77), (10, 0.796, 0.610, 2.31), (11, 0.7865, 0.5575, 2.33),
             (12, 0.774, 0.397, 3.41), (13, 0.7648, 0.4527, 1.91), (14, 0.760, 0.316, 2.28),
             (16, 0.728, 0.316, 2.04), (18, 0.716, 0.422, 2.42)]
# PT-válido: colisión < 4 (cerca de 2) y d>=6 (régimen scrambling). d=2 (colis 36) y d=4 (colis 6)
# NO son Porter-Thomas aún → la XEB no es métrica honesta ahí → se excluyen del ajuste de κ̂.
CALIB = [(d, fi, fr) for (d, fi, fr, col) in CALIB_RAW if col < 4 and d >= 6]
PROVENANCE = "ibm_kingston (metal real) 2D-random Porter-Thomas n=12, 9 jobs/2048 shots, 2026-06-22"


def _per_layer_e(F, d):
    return 1.0 - F ** (1.0 / d) if F > 0 else 1.0


def _kappa(point):
    d, fi, fr = point
    ei, er = _per_layer_e(fi, d), _per_layer_e(fr, d)
    return er / ei if ei > 0 else 1.0


def _median(xs):
    s = sorted(xs); n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def fit(calib=CALIB, alpha=0.10):
    """Ajusta κ̂ y la banda conformal por residuos leave-one-out (LOO).

    Returns dict: kappa_hat, mae_before, mae_after, conformal_q (residuo a 1-alpha), n, coverage.
    """
    kappas = [_kappa(p) for p in calib]
    kappa_hat = _median(kappas)
    res_before, res_after = [], []
    for i, (d, fi, fr) in enumerate(calib):
        res_before.append(abs(fi - fr))                       # error SIN corregir
        loo = _median([kappas[j] for j in range(len(calib)) if j != i])
        fr_pred = (1.0 - loo * _per_layer_e(fi, d)) ** d      # predicción corregida held-out
        res_after.append(abs(fr_pred - fr))
    # cuantil conformal vía el MARCO ÚNICO (conformal_core, acción D) — una sola implementación
    from conformal_core import residual_quantile
    q, coverage, n = residual_quantile(res_after, alpha)
    return {"kappa_hat": round(kappa_hat, 3), "mae_before": round(sum(res_before) / max(1, n), 3),
            "mae_after": round(sum(res_after) / max(1, n), 3), "conformal_q": (round(q, 3) if q is not None else None),
            "coverage_target": coverage, "n": n, "provenance": PROVENANCE, "framework": "conformal_core",
            "direction": ("hardware PEOR que lo inferido (κ̂>1): aprieta el techo" if kappa_hat > 1
                          else "hardware mejor que lo inferido (κ̂<1): extiende el techo"),
            "note": "9 puntos PT-válidos propios (metal real, cobertura 90%); κ̂>1 revierte el artefacto Aer; "
                    "corrección de 1er orden -> el valor es la banda + el SIGNO."}


def corrected_fidelity(F_inf, depth, model=None):
    """Aplica la corrección aprendida: F_real ≈ (1 - κ̂·e_inf)^depth, con banda conformal ±q."""
    m = model or fit()
    fr = (1.0 - m["kappa_hat"] * _per_layer_e(F_inf, depth)) ** depth
    q = m["conformal_q"]
    return {"F_inferred": round(F_inf, 4), "F_corrected": round(fr, 4),
            "band": ([round(max(0, fr - q), 4), round(min(1, fr + q), 4)] if q is not None else "uncovered (n too small)"),
            "kappa_hat": m["kappa_hat"]}


def corrected_depth_ceiling(e_per_layer_inferred, budget=0.10, model=None):
    """Techo de profundidad CORREGIDO: depth donde F_real = 1-budget, con κ̂ (vs el conservador κ=1).

    Returns: {conservative (κ=1), corrected (κ̂), gain_factor}. e_per_layer_inferred = error 2q por capa.
    """
    m = model or fit()
    def d_at(e):
        return int(math.log(1 - budget) / math.log(1 - e)) if 0 < e < 1 else None
    cons = d_at(e_per_layer_inferred)
    corr = d_at(m["kappa_hat"] * e_per_layer_inferred)
    return {"conservative_depth": cons, "corrected_depth": corr,
            "gain_factor": round(corr / cons, 2) if cons else None, "kappa_hat": m["kappa_hat"],
            "budget": budget}


if __name__ == "__main__":
    m = fit(alpha=0.10)   # con n=9 PT-válidos, la cobertura conformal con banda FINITA llega a 90%
    print("=== corrección aprendida + conformal del sesgo de inferencia hardware (DATOS PROPIOS) ===")
    print("  κ̂ (penalización de error por correlación REAL) = %.3f  (e_real ≈ κ̂·e_inf)" % m["kappa_hat"])
    print("  DIRECCIÓN: %s" % m["direction"])
    print("  MAE de fidelidad ANTES de corregir: %.3f" % m["mae_before"])
    print("  MAE DESPUÉS (leave-one-out, held-out): %.3f  -> de %.0f%% a %.0f%%"
          % (m["mae_after"], m["mae_before"] * 100, m["mae_after"] * 100))
    print("  banda conformal (cobertura %.0f%%, n=%d): ±%s  (9 PT-válidos -> 90%% alcanzado)"
          % (m["coverage_target"] * 100, m["n"], m["conformal_q"]))
    print("  %s" % m["note"])
    print("\n  techo de profundidad (CZ medido ~1.85e-3, ~6 CZ/capa en cadena n=12, budget 10%):")
    c = corrected_depth_ceiling(1.0 - (1.0 - 1.85e-3) ** 6)   # ~6 CZ por capa -> error/capa efectivo real
    print("    conservador κ=1: %s capas · corregido κ̂: %s capas · factor %sx (<1 = APRIETA, metal real)"
          % (c["conservative_depth"], c["corrected_depth"], c["gain_factor"]))

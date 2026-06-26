#!/usr/bin/env python3
"""conformal_core — el MARCO conformal único de Atlas (acción D del meta-análisis).

Antes había dos capas conformal separadas:
  - atlas_conformal (ruta): cobertura selectiva por riesgo — Wilson UB sobre el error held-out
    en el umbral tau (clasificación: ¿la ruta es correcta?).
  - atlas_conformal_hardware (reachability): banda de regresión — cuantil de residuos leave-one-out
    (regresión: ¿cuánto se desvía la fidelidad inferida de la medida?).

Son DOS instancias del MISMO principio: **cobertura distribution-free en datos held-out**. Este
módulo expone los dos primitivos para que ambas capas llamen una sola implementación:
  - wilson_upper(k, n)            -> cota superior de error (clasificación / riesgo selectivo)
  - residual_quantile(res, alpha) -> cuantil conformal finito-muestral (regresión / banda)

Ambos son honestos con n pequeño: si no se puede cubrir alpha, lo dicen (no inventan banda).
"""
from __future__ import annotations
import math

Z_ONE_SIDED_95 = 1.645


def wilson_upper(k, n, z=Z_ONE_SIDED_95):
    """Cota superior Wilson de la tasa de error k/n (clasificación). One-sided por defecto (95%)."""
    if n == 0:
        return 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return min(1.0, (c + m) / d)


def residual_quantile(residuals, alpha=0.10):
    """Cuantil conformal finito-muestral de residuos held-out (regresión).

    Índice = ceil((n+1)(1-alpha)); si excede n, la cobertura alpha NO es alcanzable con esta n →
    devuelve None (banda no-cubierta), HONESTO en vez de inventar. Devuelve (q, coverage, n).
    """
    r = sorted(abs(x) for x in residuals)
    n = len(r)
    if n == 0:
        return None, 1 - alpha, 0
    k = math.ceil((n + 1) * (1 - alpha))
    return (r[k - 1] if k <= n else None), 1 - alpha, n


def max_coverage_for_n(n):
    """La cobertura MÁXIMA con banda finita para n puntos: 1 - 1/(n+1). (n=5 -> ~0.83)."""
    return n / (n + 1) if n > 0 else 0.0


def calibrate(kind, data, alpha=0.10):
    """Entrada ÚNICA de calibración (acción D completa): un solo objeto, dos modos.

    kind='classification' (data=(k,n)) -> {error_ub, coverage} vía wilson_upper (ruta).
    kind='regression'     (data=residuals) -> {band, coverage, n} vía residual_quantile (reachability).
    """
    if kind == "classification":
        k, n = data
        return {"mode": kind, "error_ub": wilson_upper(k, n), "coverage": 0.95, "framework": "conformal_core"}
    if kind == "regression":
        q, cov, n = residual_quantile(data, alpha)
        return {"mode": kind, "band": q, "coverage": cov, "n": n, "framework": "conformal_core",
                "max_coverage_for_n": round(max_coverage_for_n(n), 3)}
    raise ValueError("kind debe ser 'classification' o 'regression'")


def framework():
    return {"principle": "distribution-free held-out coverage",
            "classification": "wilson_upper (selective risk UB) -> atlas_conformal (route)",
            "regression": "residual_quantile (LOO band) -> atlas_conformal_hardware (reachability)",
            "note": "una sola implementación de cada primitivo; dos aplicaciones, un marco."}


if __name__ == "__main__":
    print("conformal_core — marco unico:", framework()["principle"])
    print("  wilson_upper(1, 25) =", round(wilson_upper(1, 25), 4))
    print("  residual_quantile([.075,.098,.147,.215,.170], 0.20) =", residual_quantile([.075, .098, .147, .215, .170], 0.20))
    print("  max coverage n=5:", round(max_coverage_for_n(5), 3), "· n=9:", round(max_coverage_for_n(9), 3))

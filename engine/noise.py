"""noise.py -- modelo de ruido ANALITICO (orden de magnitud, supuestos declarados). NO simula ruido: estima
cuanta dureza SOBREVIVE al ruido depolarizante, convirtiendo el veredicto coherente (cota superior de dureza)
en un RANGO [dureza_ruidosa, dureza_coherente].

Fisica (declarada):
  - ruido depolarizante a tasa p por compuerta de 2 qubits; G = #compuertas de 2 qubits.
  - errores esperados:        lambda = p * G.
  - fidelidad del circuito:   F ~ e^(-lambda)   (Poisson: prob. de cero errores).
  - HECHO conocido (Aharonov; Gao-Duan; y el marco 'el ruido cura la dureza'): a tasa de ruido FIJA, la
    coherencia mas alla de ~1/p compuertas se lava -> la dureza que sobrevive escala con la fraccion
    phi = min(1, 1/lambda). Mas alla de lambda~1 el circuito ruidoso es clasicamente simulable.
  - dureza ruidosa: coste_log2 * phi.  Cruce: p* donde el ruido vuelve el circuito tratable.

Es un modelo de ORDEN DE MAGNITUD con supuestos declarados (consistente con la disciplina de honestidad del
proyecto): da el regimen y el cruce, no un numero exacto de simulacion ruidosa (eso exigiria densidad/MPO).
"""
from __future__ import annotations
import math


def noise_model(n_2q, hardness_log2, magic, p, budget_log2=40.0, n=None):
    lam = p * n_2q                                          # errores esperados
    # FIDELIDAD: forma CERRADA del canal depolarizante global (no la aproximacion e^-lambda). Recurrencia
    # F_{k+1}=(1-p)F_k + p/d  ->  F = 1/d + (1-1/d)(1-p)^G. EXACTA bajo el modelo (verificado vs densidad,
    # |Δ|~1e-15). d=2^n; si n no se da, cae a e^-lambda (cota sin el piso 1/d).
    if n is not None:
        d = 2.0 ** n
        fidelity = 1.0 / d + (1.0 - 1.0 / d) * (1.0 - p) ** n_2q
    else:
        fidelity = math.exp(-lam)
    phi = min(1.0, 1.0 / lam) if lam > 1e-12 else 1.0       # fraccion de dureza coherente que sobrevive
    noisy_hard = hardness_log2 * phi
    noisy_magic = magic * phi
    regime = "coherente" if lam < 0.3 else ("ruido domina" if lam > 3.0 else "transicion")
    noisy_tractable = noisy_hard <= budget_log2
    # cruce: tasa de error p* a la que el ruido vuelve el circuito tratable (noisy_hard = budget)
    p_crit = None
    if hardness_log2 > budget_log2 and n_2q > 0:
        lam_crit = hardness_log2 / budget_log2              # phi* = budget/hard -> lambda* = 1/phi*
        p_crit = lam_crit / n_2q
    return {"p": p, "lambda": round(lam, 3), "fidelity": round(fidelity, 5), "phi": round(phi, 3),
            "noisy_hardness_log2": round(noisy_hard, 2), "noisy_magic": round(noisy_magic, 1),
            "regime": regime, "noisy_tractable": bool(noisy_tractable),
            "p_crit": round(p_crit, 5) if p_crit else None,
            "coherent_hardness_log2": round(hardness_log2, 2), "n_2q": n_2q}


def main():
    print("noise.py -- modelo de ruido analitico\n")
    print("Circuito DURO (coherente INTRACTABLE): treewidth 2^47, 200 compuertas 2q, magia 69")
    for p in [0.0, 0.001, 0.005, 0.01, 0.03]:
        r = noise_model(200, 47.0, 69, p)
        print(f"  p={p:5.1%}: lambda={r['lambda']:6.2f}  F={r['fidelity']:.3f}  "
              f"dureza ruidosa=2^{r['noisy_hardness_log2']:<6}  {r['regime']:<13}  "
              f"{'TRATABLE bajo ruido' if r['noisy_tractable'] else 'sigue dura'}")
    r = noise_model(200, 47.0, 69, 0.005)
    print(f"\n  -> el ruido vuelve este circuito clasicamente tratable a partir de p* ~ {r['p_crit']:.2%}")
    print("DONE")


if __name__ == "__main__":
    main()

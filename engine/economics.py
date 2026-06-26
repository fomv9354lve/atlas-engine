"""economics.py -- el caso economico MEDIDO (no ilustrativo). Convierte la dureza en dolares con supuestos
declarados y pricing publicado.

Lo que medimos/derivamos (cada numero trazable):
  - tiempo de simulacion clasica REAL: cronometramos la evaluacion MPS (quimb) del circuito.  [MEDIDO]
  - coste QPU por evaluacion: shots(precision eps) x $/shot del vendor + task fee.              [PRICING PUBLICADO]
  - coste clasico por evaluacion: t_clasico(s) x tarifa CPU cloud.                                [MEDIDO x tarifa]
  - ahorro/eval = QPU - clasico; ahorro/campana = ahorro/eval x #evaluaciones.                    [DERIVADO]
  - speedup = t_QPU / t_clasico  (t_QPU = shots x tiempo_por_shot + cola).                         [DERIVADO]

Supuestos por defecto (declarados, editables):
  eps=0.01 (precision 1%) -> shots = 1/eps^2 = 10,000 (estimador de valor esperado, varianza 1/N).
  vendor = IonQ Forte via AWS Braket (Aria=legacy). campana = 1,000 evaluaciones (tipico VQE/QAOA).
Pricing PUBLICADO (~2025, AWS Braket / IBM Cloud). Si cambian las tarifas, cambian los numeros -- trazable.
"""
from __future__ import annotations
import time
import quimb.tensor as qtn
from ground_truth import _build

# Pricing snapshot — DATED + per-provider model (audit P0). Each figure is traceable to
# a public source with the snapshot date. AWS Braket = per-task + per-shot; IBM Quantum
# = per-runtime-SECOND (NOT per-shot) -> cross-provider shot comparison needs a runtime
# model, so IBM's number is an order-of-magnitude proxy, flagged below. If tariffs change
# the numbers change -- that is why they carry date + source + model, not hidden.
PRICING_SNAPSHOT_DATE = "2026-06-22"
PRICING_SOURCES = {"aws": "https://aws.amazon.com/braket/pricing/",
                   "ibm": "https://www.ibm.com/quantum/pricing"}
PRICING = {
    # VENDOR CORRECTION (audit P1-1): IonQ 'Aria' es PRIOR-GENERATION. El device IonQ vigente en AWS
    # Braket es 'IonQ Forte' ($0.30/task + $0.08/shot). Forte es el default; Aria queda como LEGACY
    # (flagged) para reproducir configs viejas y que el cambio sea auditable.
    "IonQ Forte (AWS Braket)":  {"shot": 0.08,    "task": 0.30, "shot_us": 200,
                                 "per_shot_usd": 0.08, "per_task_usd": 0.30,
                                 "vendor": "IonQ", "device": "Forte", "status": "current",
                                 "model": "per_task+per_shot", "date": PRICING_SNAPSHOT_DATE,
                                 "src": "AWS Braket pricing (on-demand IonQ Forte: $0.30/task + $0.08/shot)"},
    "IonQ Aria (AWS Braket) [LEGACY]": {"shot": 0.03, "task": 0.30, "shot_us": 200,
                                 "per_shot_usd": 0.03, "per_task_usd": 0.30,
                                 "vendor": "IonQ", "device": "Aria", "status": "legacy",
                                 "model": "per_task+per_shot", "date": PRICING_SNAPSHOT_DATE,
                                 "src": "PRIOR-GENERATION; usa 'IonQ Forte (AWS Braket)' para cotizaciones vigentes"},
    "Rigetti (AWS Braket)":     {"shot": 0.00035, "task": 0.30, "shot_us": 1,
                                 "model": "per_task+per_shot", "date": PRICING_SNAPSHOT_DATE,
                                 "src": "AWS Braket pricing page"},
    "IBM (pay-as-you-go)":      {"shot": 0.0,     "task": 0.0,  "per_second": 1.60,
                                 "model": "per_runtime_second (NOT per_shot; proxy via shot_us)",
                                 "date": PRICING_SNAPSHOT_DATE,
                                 "src": "IBM Quantum pay-as-you-go (~$96/min ~ $1.60/s); shot->runtime "
                                        "conversion required for a fair per-shot comparison"},
}
CPU_RATE_HR = 0.10          # CPU cloud on-demand (~c-series Graviton/x86 on-demand), USD/hora
QUEUE_S = 60.0             # cola tipica de un job cloud quantum (conservador), segundos


def classical_sim_seconds(n, circuit, max_bond=256):
    """MIDE el tiempo real de evaluar el circuito clasicamente via MPS (quimb)."""
    t0 = time.time()
    circ = qtn.CircuitMPS(n, gate_opts={"max_bond": max_bond, "cutoff": 1e-10})
    _build(circ, circuit)
    _ = circ.psi.max_bond()                                  # fuerza la contraccion
    return time.time() - t0


ERR_2Q = 0.005          # error por compuerta de 2 qubits (~99.5% fidelidad, IonQ Forte ~2025). Declarado.


def _circuit_factors(circuit):
    """El coste QPU NO es fijo: depende del circuito. Devuelve (overhead de mitigacion de error, factor de
    tiempo por shot). Mas compuertas de 2 qubits -> mas error -> mas shots para mitigarlo (ZNE ~exp); mas
    profundidad -> pulso mas largo -> mas tiempo por shot. Modelo de orden de magnitud, supuestos declarados."""
    two_q = sum(1 for g in circuit if g and g[0] in ("cx", "cnot"))
    depth = max(1, len(circuit))
    import math
    mitig = min(math.exp(2.0 * two_q * ERR_2Q), 1000.0)     # overhead de shots por mitigacion (cap 1000x)
    t_factor = 1.0 + depth / 200.0                          # tiempo por shot crece con la profundidad
    return round(mitig, 3), round(t_factor, 3), two_q, depth


def economics(n, circuit, tractable, treewidth_log2=8, shots=10000, eps=0.01,
              vendor="IonQ Forte (AWS Braket)", campaign=1000):
    p = PRICING[vendor]
    mitig, t_factor, two_q, depth = _circuit_factors(circuit)   # <- el QPU ahora DEPENDE del circuito
    shots_eff = round(shots * mitig)                            # shots efectivos (con mitigacion de error)
    qpu_eval = round(p.get("task", 0) + shots_eff * p.get("shot", 0)
                     + (p.get("per_second", 0) * shots_eff * p.get("shot_us", 1) * t_factor * 1e-6), 2)
    t_qpu = shots_eff * p.get("shot_us", 100) * t_factor * 1e-6 + QUEUE_S
    out = {"shots": shots, "shots_eff": shots_eff, "mitig": mitig, "t_factor": t_factor,
           "two_q_gates": two_q, "depth": depth, "eps": eps, "vendor": vendor, "campaign": campaign,
           "qpu_cost_eval": qpu_eval, "t_qpu_s": round(t_qpu, 1), "src": p.get("src", ""),
           # manifest auditable (lo que la diligence pedía: fecha/región/device/fórmula/fuente)
           "pricing_manifest": {
               "as_of": PRICING_SNAPSHOT_DATE, "region": "us-east (AWS Braket / IBM default)",
               "device": vendor, "model": p.get("model", "per_task+per_shot"),
               "shots_formula": "shots_eff = round(shots × mitig); qpu_cost = task + shots_eff×shot + per_second×shots_eff×shot_us×t_factor×1e-6",
               "sources": PRICING_SOURCES,
               "caveat": "precios cambian; región/device alteran el costo; runtime clásico es MEDIDO en esta máquina (no portable)."}}

    if tractable:
        t_cls = classical_sim_seconds(n, circuit)            # MEDIDO
        cls_eval = (t_cls / 3600.0) * CPU_RATE_HR
        # GUARD (VULN-2): si el tiempo clasico cae por debajo de la resolucion de medida (~1ms), el cociente
        # t_qpu/t_cls diverge a numeros sin sentido (10^5x) -> el circuito es TRIVIAL, no hay 'speedup' que
        # reportar. Marcamos trivial y NO emitimos un speedup enganoso.
        trivial = t_cls < 1e-3
        out.update({"classical_sim_s": round(t_cls, 4), "classical_cost_eval": round(cls_eval, 6),
                    "savings_eval": round(qpu_eval - cls_eval, 2),
                    "savings_campaign": round((qpu_eval - cls_eval) * campaign, 0),
                    "trivial": trivial,
                    "speedup": None if trivial else round(t_qpu / t_cls, 0)})
    else:
        # intractable exacto: coste clasico ~ 2^treewidth FLOPs (estimacion, declarada)
        # BASELINE DECLARADO: 1e13 FLOP/s = ~1 GPU clase A100 (FP64 ~10 TFLOPS sostenido, 2020+).
        # Antes 1e11 (1 core ~2015) subestimaba ~100x el hardware moderno (B-4 del audit). El supuesto
        # se EXPONE en la respuesta (hpc_flops_per_s) para que sea auditable y ajustable.
        HPC_FLOPS = 1e13
        flops = 2.0 ** treewidth_log2
        t_cls_hpc = flops / HPC_FLOPS
        cls_eval = (t_cls_hpc / 3600.0) * CPU_RATE_HR
        out.update({"classical_sim_s": None, "hpc_flops_log2": round(treewidth_log2, 1),
                    "hpc_flops_per_s": HPC_FLOPS, "hpc_hw_baseline": "~1 GPU A100 (FP64 ~10 TFLOPS)",
                    "hpc_cost_eval": round(cls_eval, 2), "hpc_time_s": round(t_cls_hpc, 2),
                    "qpu_advantage": "exponencial" if treewidth_log2 > 40 else "marginal"})
    return out


def main():
    import sys
    sys.path.insert(0, "src")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from atlas import build_target, decompose
    print("economics -- caso economico MEDIDO (no ilustrativo)\n")
    circ = decompose(build_target(12, 6, "high", "high", "core", "low"))
    e = economics(12, circ, tractable=True, treewidth_log2=12)
    print(f"  circuito tratable (n=12):")
    print(f"    sim clasica MEDIDA: {e['classical_sim_s']*1000:.1f} ms  -> coste ${e['classical_cost_eval']:.6f}/eval")
    print(f"    QPU ({e['vendor']}): ${e['qpu_cost_eval']}/eval  ({e['shots']} shots, eps={e['eps']})")
    print(f"    AHORRO: ${e['savings_eval']}/eval  -> ${e['savings_campaign']:,.0f} en campana de {e['campaign']} evals")
    print(f"    SPEEDUP: {e['speedup']:,.0f}x  (QPU {e['t_qpu_s']}s vs clasico {e['classical_sim_s']*1000:.0f}ms)")
    print("\n  Todos los numeros: MEDIDOS (tiempo clasico) o PRICING PUBLICADO (QPU), bajo supuestos declarados.")
    print("DONE")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""qpu_calibration_pt — genera DATOS PROPIOS para la corrección conformal (Gap #2).

La corrección de atlas_conformal_hardware usa n=5 puntos cross-session (1D no-PT). Para llevar
la cobertura a 90% con datos PROPIOS, necesitamos >=9 puntos de circuitos genuinamente
scrambling (Porter-Thomas) — donde la XEB es la métrica correcta — corridos en ibm_kingston.

Diseño: 2D-random scrambling a n=12 (statevector-computable -> ideal exacto), rampa de 9
profundidades. Cada job da un punto (F_inferido 1er-orden, F_medido vía linear-XEB normalizada
por la colisión REAL). Al recoger (qpu_collect-style) se ajusta κ̂ con banda conformal 90%.

Fire-and-forget, ~18s de cuota. Ideales/XEB se computan al recoger desde el QASM registrado.
"""
from __future__ import annotations
import json, os, random, sys
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))

N = 12
DEPTHS = [2, 4, 6, 8, 10, 12, 14, 16, 18]   # 9 puntos -> cobertura conformal 90% (necesita >=9)


def random_2d_scrambling(n, depth, seed):
    """Brickwork 2D-ish random: capas de CX vecinos (grid 3x4) + 1q random {h,s,t} -> Porter-Thomas."""
    rng = random.Random(seed)
    R, C = 3, 4
    idx = lambda r, c: r * C + c
    edges = []
    for r in range(R):
        for c in range(C - 1): edges.append((idx(r, c), idx(r, c + 1)))
    for r in range(R - 1):
        for c in range(C): edges.append((idx(r, c), idx(r + 1, c)))
    L = ["OPENQASM 2.0;", 'include "qelib1.inc";', "qreg q[%d];" % n]
    for q in range(n): L.append("h q[%d];" % q)
    for d in range(depth):
        rng.shuffle(edges)
        used = set()
        for (u, v) in edges:
            if u not in used and v not in used:
                L.append("cx q[%d],q[%d];" % (u, v)); used |= {u, v}
        for q in range(n):
            L.append("%s q[%d];" % (rng.choice(["h", "s", "t"]), q))   # 1q random -> scrambling + magia
    return "\n".join(L) + "\n"


def plan():
    return [("pt_n12_d%d" % d, random_2d_scrambling(N, d, 100 + d), {"n": N, "depth": d}) for d in DEPTHS]


def main():
    submit = os.environ.get("QPU_SUBMIT") == "1"
    from atlas import cost_atlas, safe_parse
    import numpy as np
    from qiskit.qasm2 import loads as qload
    from qiskit.quantum_info import Statevector
    js = plan()
    print("=== plan calibración PT (n=12, 2D-random) + chequeo de colisión (PT≈2) ===")
    for name, qasm, meta in js:
        pn, circ, _ = safe_parse(qasm); r = cost_atlas(pn, circ)
        p = np.abs(Statevector.from_instruction(qload(qasm)).data) ** 2   # ideal exacto
        collision = float((p ** 2).sum() * 2 ** pn)                       # PT -> ~2
        meta["collision"] = round(collision, 2); meta["route"] = (r.get("route_adjudication") or {}).get("route")
        print("  %-12s d=%2d  colisión=%.2f %s  ruta=%s" % (name, meta["depth"], collision,
              "(PT-like)" if collision < 3 else "(picada, no-PT aún)", meta["route"]))
    if not submit:
        print("\nDRY-RUN. QPU_SUBMIT=1 para encolar 9 jobs (~18s cuota, fire-and-forget).")
        return
    d = json.load(open(os.path.expanduser(os.environ.get("QISKIT_IBM_TOKEN_FILE", "~/Downloads/apikey.json"))))
    tok = d.get("apiKey") or d.get("token") or d.get("apikey")
    from qiskit import transpile
    from qiskit.qasm2 import loads as qload2
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
    svc = QiskitRuntimeService(channel="ibm_quantum_platform", token=tok)
    b = svc.backend("ibm_kingston")
    reg = {}
    for name, qasm, meta in js:
        qc = qload2(qasm); qc.measure_all()
        isa = transpile(qc, b, optimization_level=1)
        job = Sampler(mode=b).run([isa], shots=2048)
        reg[name] = {"job_id": job.job_id(), "qasm": qasm, "meta": meta, "status": str(job.status())}
        print("  ENCOLADO %-12s %s %s" % (name, job.job_id(), job.status()))
    f = os.path.join(ROOT, "benchmarks", "qpu_jobs.json")
    prev = json.load(open(f)) if os.path.isfile(f) else {}
    prev["calibration_pt"] = reg
    open(f, "w").write(json.dumps(prev, indent=2))
    print("\nregistro -> benchmarks/qpu_jobs.json (calibration_pt: %d jobs)" % len(reg))


if __name__ == "__main__":
    main()

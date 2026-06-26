#!/usr/bin/env python3
"""QPU validation — close the DEMONSTRABLE side end-to-end on real IBM hardware.

Honest scope (read this): a QPU gives NOISY samples, not ground truth, and does NOT
prove classical hardness. So this does NOT certify the hard regime. What it DOES, with
a tiny slice of quota:
  (1) For circuits Atlas calls CHEAP/CPU: run them BOTH classically (exact) and on the
      real QPU, and show the QPU's noisy samples approximately match the exact classical
      distribution -> end-to-end proof that the classical route reproduces the device,
      i.e. you did NOT need the QPU. (The audit's hardware-test-path artifact.)
  (2) Measure REAL runtime seconds -> replace the pricing proxy with a measured number.

SAFETY: DRY-RUN by default (no quota spent: transpiles, simulates classically, prints
the plan + estimated usage). Submits to the real QPU ONLY if env QPU_SUBMIT=1.
Credentials: read from env QISKIT_IBM_TOKEN (+ optional QISKIT_IBM_INSTANCE). This
script never prints or stores the token. Circuits are tiny (n<=5, 1024 shots) to stay
well inside a 10-min/month budget.

Run dry (safe):   python3 benchmarks/qpu_validation.py
Run for real:     QISKIT_IBM_TOKEN=... QPU_SUBMIT=1 python3 benchmarks/qpu_validation.py

Backend: ibm_kingston (Heron r2, 156 qubits, basis gates cz/id/rx/rz/rzz/sx/x; 2Q error
~2.0e-3, readout ~7.9e-3, T1~241µs/T2~144µs). Toda puerta no nativa (h/cx/t) se transpila.
Ficha completa en ``IBM_KINGSTON.md``. NB: para correr SIN bloquear (jobs en paralelo) usa
``qpu_submit.py`` — este script llama result() y espera a cada job en orden.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Statevector


def tiny_circuits():
    """Two small circuits Atlas should call CHEAP (classically reproducible)."""
    a = QuantumCircuit(4, name="ghz4")            # GHZ: entangled but trivially simulable
    a.h(0); a.cx(0, 1); a.cx(1, 2); a.cx(2, 3)
    b = QuantumCircuit(5, name="cliffordT5")       # Clifford + a couple T (low magic, local)
    for i in range(5):
        b.h(i)
    b.cx(0, 1); b.cx(1, 2); b.t(2); b.cx(2, 3); b.t(3); b.cx(3, 4)
    return [a, b]


def ideal_probs(qc):
    """Exact classical reference distribution (this is the 'you didn't need a QPU' proof)."""
    sv = Statevector.from_instruction(qc)
    p = np.abs(sv.data) ** 2
    return {format(i, "0%db" % qc.num_qubits): float(p[i]) for i in range(len(p)) if p[i] > 1e-9}


def tvd(p, q):
    keys = set(p) | set(q)
    return 0.5 * sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def atlas_verdict(qc):
    try:
        from atlas_certificate import certificate
        from qiskit.qasm2 import dumps
        c = certificate(dumps(qc))
        return c["route"], c["confidence"]["tier"]
    except Exception as e:
        return "n/a", "n/a (" + type(e).__name__ + ")"


def main():
    submit = os.environ.get("QPU_SUBMIT") == "1"
    connect_only = os.environ.get("QPU_CONNECT_ONLY") == "1"
    live = submit or connect_only
    shots = 1024
    circs = tiny_circuits()
    mode = "CONNECT-ONLY (0 quota)" if connect_only else ("LIVE SUBMIT" if submit else "DRY-RUN")
    print(f"=== QPU validation ({mode}) ===")
    print("Atlas verdict for each circuit (should be CPU/cheap -> classically reproducible):")
    for qc in circs:
        rt, tier = atlas_verdict(qc)
        print(f"  {qc.name:<12} n={qc.num_qubits}  atlas_route={rt} tier={tier}")

    if not live:
        print("\nDRY-RUN: no quota spent. Classical reference distributions:")
        for qc in circs:
            ip = ideal_probs(qc)
            top = sorted(ip.items(), key=lambda kv: -kv[1])[:4]
            print(f"  {qc.name}: top outcomes {[(k, round(v,3)) for k,v in top]}")
        print("\nTo run on the real QPU (spends a little quota), set in your shell:")
        print("  export QISKIT_IBM_TOKEN=<your token from quantum.cloud.ibm.com>")
        print("  QPU_SUBMIT=1 python3 benchmarks/qpu_validation.py")
        print("Estimated: 2 jobs x 1024 shots on the least-busy device; small-circuit "
              "runtime is typically a few seconds each (well inside 10 min/month).")
        return

    # ---- LIVE PATH: token from env OR from a downloaded apikey.json. NEVER printed. ----
    tok = os.environ.get("QISKIT_IBM_TOKEN")
    tf = os.environ.get("QISKIT_IBM_TOKEN_FILE")
    if not tok and tf and os.path.isfile(tf):
        import json as _json
        try:
            d = _json.load(open(tf, encoding="utf-8"))
            tok = d.get("apiKey") or d.get("token") or d.get("apikey") or d.get("api_key")
        except Exception:
            tok = (open(tf, encoding="utf-8").read().strip() or None)  # raw token file
    if not tok:
        print("No token (set QISKIT_IBM_TOKEN or QISKIT_IBM_TOKEN_FILE). Aborting."); return
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
    svc_kw = {"channel": "ibm_quantum_platform", "token": tok}
    if os.environ.get("QISKIT_IBM_INSTANCE"):
        svc_kw["instance"] = os.environ["QISKIT_IBM_INSTANCE"]
    service = QiskitRuntimeService(**svc_kw)
    backend = service.least_busy(operational=True, simulator=False)
    print(f"\nbackend: {backend.name} ({backend.num_qubits}q)  [credential OK, 0 quota spent so far]")
    if os.environ.get("QPU_CONNECT_ONLY") == "1":
        print("CONNECT-ONLY: credential validated + backend selected. NO jobs submitted "
              "(0 quota). Re-run without QPU_CONNECT_ONLY to submit the 2 tiny jobs.")
        return
    rows = []
    for qc in circs:
        m = qc.copy(); m.measure_all()
        isa = transpile(m, backend, optimization_level=1)
        sampler = Sampler(mode=backend)
        t0 = time.time()
        job = sampler.run([isa], shots=shots)
        res = job.result()
        wall = time.time() - t0
        # counts
        creg = list(res[0].data.__dict__.keys())[0]
        counts = getattr(res[0].data, creg).get_counts()
        tot = sum(counts.values())
        qpu_p = {k.replace(" ", ""): v / tot for k, v in counts.items()}
        ip = ideal_probs(qc)
        d = tvd(ip, qpu_p)
        usage = None
        try:
            usage = job.usage()
        except Exception:
            pass
        print(f"  {qc.name}: TVD(ideal,qpu)={d:.3f}  wall={wall:.1f}s  usage={usage}")
        rows.append({"circuit": qc.name, "n": qc.num_qubits, "backend": backend.name,
                     "shots": shots, "tvd_ideal_vs_qpu": round(d, 4),
                     "wall_s": round(wall, 1), "usage": str(usage),
                     "atlas_route": atlas_verdict(qc)[0]})
    out = ROOT / "benchmarks" / "results_scaled" / "benchmark_results_hardware.csv"
    import csv
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    print(f"\nwrote {out.relative_to(ROOT)}")
    print("Reading: low TVD => the exact classical distribution reproduces the (noisy) "
          "QPU within device error => Atlas's 'cheap/CPU' verdict is validated on real "
          "hardware end-to-end. Measured runtime/usage anchors the pricing model.")


if __name__ == "__main__":
    main()

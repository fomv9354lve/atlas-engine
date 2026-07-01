"""Generate REAL MQT Bench algorithm-level circuits (cda-tum/mqt-bench) and write
them as OpenQASM 2.0 into ./qasm/ with an mqt_ prefix. These are the standard
community algorithm benchmarks (Grover, QFT, AE, QAOA, VQE, QPE, Shor, GHZ,
W-state, random, etc.) -- genuinely external/published, not self-generated.

Each circuit is produced at BenchmarkLevel.ALG (the abstract algorithm circuit,
device-independent). We dump qasm2 for Atlas's parser. Failures are reported,
not faked.
"""
from __future__ import annotations
import os, sys, json
from mqt.bench import get_benchmark, BenchmarkLevel
from qiskit.qasm2 import dumps

HERE = os.path.dirname(os.path.abspath(__file__))
QDIR = os.path.join(HERE, "qasm")
os.makedirs(QDIR, exist_ok=True)

# (benchmark_name, circuit_size). ALG level. Spread of sizes/families.
PICKS = [
    ("ae", 12), ("ae", 18),
    ("grover", 8), ("grover", 12),
    ("qpeexact", 10), ("qpeexact", 16),
    ("qpeinexact", 14),
    ("qaoa", 12),
    ("qftentangled", 20), ("qftentangled", 40),
    ("qwalk", 12),
    ("graphstate", 30), ("graphstate", 60),
    ("dj", 40), ("dj", 80),
    ("vqe_su2", 12),
    ("vqe_real_amp", 14),
    ("vqe_two_local", 16),
    ("qnn", 12),
    ("wstate", 50),
    ("randomcircuit", 16), ("randomcircuit", 24),
    ("cdkm_ripple_carry_adder", 18),
    ("draper_qft_adder", 16),
    ("modular_adder", 16),
    ("multiplier", 16),
    ("shor", 18),
    ("qwalk", 20),
]

manifest = []
for bench, size in PICKS:
    tag = f"mqt_{bench}_n{size}"
    try:
        qc = get_benchmark(benchmark=bench, level=BenchmarkLevel.ALG, circuit_size=size)
        n = qc.num_qubits
        qasm = dumps(qc)
        fn = os.path.join(QDIR, f"{tag}.qasm")
        with open(fn, "w") as f:
            f.write(qasm)
        manifest.append({"tag": tag, "bench": bench, "req_size": size, "n": n, "file": fn, "ok": True})
        print(f"OK   {tag}  n={n}")
    except Exception as e:
        manifest.append({"tag": tag, "bench": bench, "req_size": size, "ok": False,
                         "error": f"{type(e).__name__}: {e}"})
        print(f"FAIL {tag}  {type(e).__name__}: {e}", file=sys.stderr)

with open(os.path.join(HERE, "mqt_manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)
print(f"\ngenerated {sum(1 for m in manifest if m['ok'])}/{len(PICKS)} MQT circuits")

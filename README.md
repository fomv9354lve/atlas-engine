# Atlas — Quantum Compute Triage (open engine)

**Before you spend QPU time or a week of HPC, answer one question: does this circuit actually
need a quantum computer, or can a laptop reproduce it?** Atlas is a pre-flight *triage* — it
routes a circuit to CPU / TENSOR / HPC / ESCALATE with calibrated confidence, and prices the
decision. Live demo: **[atlas.krenniq.com](https://atlas.krenniq.com)**.

© 2026 Fco. Osvaldo Morales Vilchis · **Apache 2.0** (see `LICENSE` / `NOTICE`).

This repository is the **open engine + the reproducible benchmark corpus** — everything you need
to check the numbers yourself. No account, no quota, runs on your machine.

## Run it

```bash
python3 -m pip install -r requirements.txt        # numpy, stim, quimb, cotengra, qiskit
python3 atlas_local.py                            # full local UI at http://127.0.0.1:8791
# or, scriptable:
echo 'OPENQASM 2.0; include "qelib1.inc"; qreg q[5]; h q[0]; cx q[0],q[1]; t q[2];' \
  | python3 engine/atlas_run.py           # JSON verdict on stdout
```

See **[QUICKSTART.md](QUICKSTART.md)** for details.

## Check the numbers

Every public figure on the site maps to a data file + a script in **[REPRODUCE.md](REPRODUCE.md)**.
The headline benchmark (2,517 oracle-certified circuits, route-correctness 0.996) reproduces
standalone:

```bash
python3 engine/atlas_benchmark_bundle.py  # corpus SHA + confusion matrix + metric definition
```

- **Corpus:** `benchmarks/results_scaled/*.csv` (2,517 rows, labels from exact oracles Stim/quimb — not circular).
- **Hardware:** `benchmarks/qpu_jobs.json` + `QPU_RESULTS.md` (real ibm_kingston jobs, TVD ≈ 0.06; one device, declared scope).

## What this is — and isn't

Atlas is a compute-cost **triage** (decision-support diagnostic), **not** a proof of classical
simulability or of quantum advantage. It does not extend the classical frontier — it triages which
side of it a circuit is on. Borderline-zone verdicts are flagged as such. The benchmark headline is
**self-consistency vs. an exact same-formalism oracle**; the genuinely-hard (escalate) regime is
**unmeasured** — there is no classical ground truth there.

The scalable engine (Stim / quimb / cotengra + route adjudication + UI) is here and open. The
proprietary research arsenal (the n≤14 fold/spread engine) is not part of this release.

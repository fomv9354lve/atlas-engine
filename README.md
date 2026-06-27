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
The headline benchmark (2,517 oracle-certified circuits, self-consistency vs. an exact
same-formalism oracle = 0.996 — not "route correctness") reproduces standalone:

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

## What is open — and what isn't

**Open (Apache-2.0, in this repo):** the scalable engine (Stim / quimb / cotengra + the route
adjudicator + UI), the benchmark corpus (2,517 oracle-certified circuits), the reproduce scripts,
and the measured QPU result JSONs. Clone it and re-derive every number.

**Not open (proprietary):** the research arsenal (the n≤14 fold/spread engine) and the confidence
model trained on top of it. That is the moat — not the data. "Open engine" here does not mean the
entire system is released.

(IBM Quantum device data — job IDs, calibration, results — is IBM's data, used under IBM Quantum's
terms; it is NOT covered by Apache-2.0. See `NOTICE`.)

## Trademarks / no affiliation

Atlas is a Krenn·IQ project. Not affiliated with, endorsed by, or sponsored by IBM, IonQ, Rigetti,
IQM, AWS, or any quantum-hardware vendor. All third-party names and marks are property of their
respective owners.

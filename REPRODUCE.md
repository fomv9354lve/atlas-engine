# Reproduce every figure

Atlas's claim is "publish in a form you can check." This file maps **every public number**
on [atlas.krenniq.com](https://atlas.krenniq.com) to the exact data file and script that
produces it. Atlas's own code, corpus and scripts are Apache 2.0. (IBM Quantum device data — job
IDs, calibration, results — is IBM's data, used under IBM Quantum's terms; it is NOT covered by
Apache-2.0. See `NOTICE`.) No account, no quota — it runs on your machine.

```bash
python3 -m pip install -r requirements.txt   # numpy, stim, quimb, cotengra, qiskit
```

All paths are relative to the repo root. Scripts that hit real hardware read your IBM token
from `QISKIT_IBM_TOKEN` / `QISKIT_IBM_TOKEN_FILE` (never printed, never committed); everything
else is offline and deterministic.

---

## 1 · Benchmark accuracy + confusion matrix ("2,517 certified · route-correctness 0.996")

- **Data:** `benchmarks/results_scaled/scaled_results.csv` (800) ·
  `scaled_results_ext.csv` (90) · `scaled_results_moat.csv` (1,627) = **2,517 oracle-certified rows**.
  Labels come from exact same-formalism oracles (Clifford via Stim, small-n via statevector/MPS) —
  not from Atlas's own estimate, so the benchmark is not circular.
- **Reproduce the bundle the site serves at `/api/benchmark`:**
  ```bash
  python3 engine/atlas_benchmark_bundle.py
  ```
  Prints the corpus size + SHA, the route confusion matrix, the metric **definition**
  (0.996 = route-correctness 2506/2517, *not* "accuracy on 1 error"), the false-safety count
  with a Wilson 95% CI on the small hard subset, and the single-estimator baselines.
- **Pre-computed stats:** `benchmarks/results_scaled/scaled_stats.json` ·
  `scaled_validation_report.md`.

> Scope (stated on the site too): the headline figure is **self-consistency vs. an exact
> same-formalism oracle**, not "route-correctness" in an absolute sense. The genuinely-hard
> (escalate) regime is **unmeasured** — there is no classical ground truth there.

## 2 · Hardware validation ("TVD ≈ 0.06 on a Heron r2 device")

- **Data:** `benchmarks/qpu_jobs.json` (every job_id) · `benchmarks/QPU_RESULTS.md`
  (TVD per family) · `benchmarks/qpu_mirror_results.json` (mirror-RB).
- **Resubmit it yourself** (needs an IBM Quantum account; reads your token from env):
  ```bash
  QISKIT_IBM_TOKEN=<your-token> QPU_SUBMIT=1 python3 benchmarks/qpu_validation.py
  ```
- Result: TVD(ideal, QPU) ≈ 0.059 / 0.055 (GHZ-4, Clifford+T-5); mirror-RB per-layer error rate (r_per_layer)
  6.7 %–11.2 % readout-corrected. **Scope:** one device (`ibm_kingston`), dates 2026-06-22/24.
  An IBM job-id alone is not third-party fetchable — the result JSONs above are what make it checkable.

## 3 · Local noise model ("F anchored to measured ibm_kingston CZ/readout")

- **Data:** `benchmarks/kingston_calibration.json` (per-edge CZ / readout / T1 / SX, 156 qubits /
  176 edges, measured 2026-06-22) · `benchmarks/results_scaled/noise_local_validation.csv`.

## 4 · Calibrated confidence (isotonic + Platt + reliability diagram)

- **Script:** `engine/atlas_recalibrate.py` → reliability diagram + ECE.

## 5 · Conformal coverage (split conformal)

- **Script:** `engine/atlas_conformal.py` (core in `engine/conformal_core.py`).

## 6 · Channel capacity (bits, Miller–Madow corrected)

- **Script:** `engine/atlas_channel_capacity.py` →
  `benchmarks/results_scaled/channel_capacity.json`.

## 7 · Applicability domain (leverage AD, FalseVerify, epistemic/aleatoric)

- **Script:** `engine/atlas_applicability_domain.py` →
  `benchmarks/results_scaled/applicability_domain.json`.

## 8 · Proofreading / bits-per-second economics

- **Script:** `engine/atlas_proofreading.py` →
  `benchmarks/results_scaled/proofreading.json`.

## 9 · Simulability certificate (STRONG/FIRM/WEAK/SPLIT/NULL + hash)

- **Script:** `engine/atlas_certificate.py` — `certificate(n, circuit, budget_log2=30)`
  → level + signers + content hash. Soundness regression: `0 false-STRONG` on the certified corpus.

## 10 · Adversarial security (0 false-security verdicts)

- **Script:** `benchmarks/adversarial_attack.py` — permanent regression (irrational rotations,
  T-identity camouflage, maximal entanglement, mid-circuit measurement, permutation camouflage).

---

### Run your own circuit

```bash
echo 'OPENQASM 2.0; include "qelib1.inc"; qreg q[5]; h q[0]; cx q[0],q[1]; t q[2];' \
  | python3 engine/atlas_run.py        # JSON verdict on stdout
# or the full local UI:
python3 atlas_local.py                          # http://127.0.0.1:8791
```

### What this is and isn't

Atlas is a compute-cost **triage** (decision-support diagnostic) — *not* a proof of classical
simulability or of quantum advantage. It does not extend the classical frontier; it triages which
side of it a circuit is on. Borderline-zone verdicts are flagged as such.

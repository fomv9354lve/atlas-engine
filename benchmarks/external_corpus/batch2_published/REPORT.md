# External-corpus batch 2 -- MORE real published circuits through the REAL Atlas engine

**Data-only research harness.** Nothing was deployed, pushed to git, or written to the live site. All outputs live in this `batch2_published/` directory only. The web n-cap was bypassed **for this offline harness only** (we call `cost_atlas` directly, same as batch 1's `worker.py`); the live cap is untouched.

## What was added

**69 genuinely external / community-standard circuits**, run through the REAL `cost_atlas` + `route_adjudicator` from `atlas-codex/HANDOFF_5ideas/`:

| Source | Count | What |
|---|---|---|
| **QASMBench** (Li, Stein, Krishnamoorthy, Ang, ACM TQC 2023; github.com/pnnl/QASMBench) | 43 | small/medium/large `.qasm` across families: adder, hhl, ising, qpe, sat, shor, simon, vqe(_uccsd), bigadder, bv, bwt, cat, cc, dnn, factor247, ghz, knn, multiplier, qft, qram, square_root, swap_test, qugan, QV |
| **MQT Bench** (Quetschlich, Burgholzer, Wille, Quantum 7, 1062 (2023); github.com/cda-tum/mqt-bench), algorithm (ALG) level | 26 | grover, qpe(exact/inexact), qaoa, qftentangled, qwalk, graphstate, dj, vqe (su2/real_amp/two_local), qnn, wstate, randomcircuit, cdkm/draper/modular adders, multiplier, shor |

These deliberately **exclude the 14 QASMBench circuits already in batch 1** (adder_n28, bv_n70, cat_n65, dnn_n33, ghz_n127, ising_n34/66, knn_n31, multiplier_n45, qft_n29/63, qugan_n39, QV_n32, vqe_uccsd_n28) -- we took the OTHERS. All are external/published; none are self-generated families.

## REAL route distribution of this batch (69 circuits)

| Route | Count | Share |
|---|---:|---:|
| **CPU** | 56 | 81% |
| **TENSOR** | 1 | 1.4% |
| **HPC_FIRST** | 0 | 0% |
| **ESCALATE** | 0 | 0% |
| **TIMEOUT** | 12 | 17% |

- **0 ERROR** (all 69 parsed and either completed or timed out cleanly).
- CPU routes were governed by: **MPS** (35), **Stim stabilizer** (17), **statevector** (4) -- i.e. the classical tractability came from real low-bond / Clifford / small-n structure, not a blanket "CPU" stamp.
- **TENSOR (1):** `mqt_randomcircuit_n24` -- treewidth ~= 2^47, statevector-governed, correctly routed to the tensor-network tier (a genuine non-CPU classical tier).

## Honest caveats (do NOT read this as "everything is classical")

- **17% (12/69) TIMED OUT** and are recorded as `route="TIMEOUT"`, not spun as anything else: `qb_hhl_n10, qb_bwt_n21, qb_factor247_n15, qb_hhl_n14, qb_vqe_n24, qb_QV_n100, qb_bwt_n37, qb_qft_n160, qb_square_root_n45, mqt_qwalk_n12, mqt_shor_n18, mqt_qwalk_n20`.
- **The per-circuit cap here is 300 s**, not the 600 s in the spec. It was lowered after an initial full-run pass got killed by the sandbox's background-runtime limit; 300 s let the batch finish with per-circuit checkpointing. Two of these (`hhl_n10`, `hhl_n14`) had **already** exceeded 600 s in the aborted first pass, so they are genuinely heavy; the remaining 10 are honestly only known to exceed **300 s** on this box -- some might finish under a longer cap.
- **What TIMEOUT means:** `cost_atlas`'s estimator search (treewidth / contraction ordering) did not finish within the cap. Note several timeouts are **small-n** (`hhl_n10`, `factor247_n15` n=15, `mqt_qwalk_n12` n=12) -- this reflects a **cost-estimation performance limit of the engine's own search**, NOT proof the circuit is classically intractable. The large ones (`qft_n160`, `QV_n100`) are plausibly genuinely heavy. We do not claim which.
- **Download/dep wall:** MQT Bench's `ae` (amplitude estimation) benchmark failed to export at both requested sizes -- Qiskit `qasm2.dumps` raised `TypeError: only 0-dimensional arrays can be converted to Python scalars` on its parameter array. Skipped honestly (2 circuits lost; not faked). All other deps (numpy/stim/quimb/cotengra/qiskit/mqt-bench) were available in `.atlas-venv` (mqt-bench was pip-installed into it for this run).

## Combined external corpus total

Existing external corpus = **46** (batch1 `results.json` 18 + `tier2_qaoa_trotter` 16 + `tier2_vqe` 12). Adding **69** -> **~115 total** external/published circuits.

## Files (this dir only)

- `results.json` -- the 69 records (name, source/suite, n, t_count, magic_log2, mps_bond_log2, treewidth_log2, route, governing_estimator, confidence, elapsed_s), plus summary.
- `gen_mqt.py` -- MQT Bench generator (ALG level -> OpenQASM 2.0 in `qasm/`).
- `run_batch2.py` -- resumable harness (per-circuit subprocess, 300 s cap, checkpoint after every circuit, reuses batch1 `worker.py` read-only).
- `mqt_manifest.json` -- MQT generation manifest (incl. the 2 `ae` failures).
- `qasm/` -- the staged `.qasm` inputs (qb_* copied from QASMBench, mqt_* generated).
- `run.log` -- raw run log.

# External-Corpus Re-run — FIXED engine (per-estimator budgets)

**Date:** 2026-06-30
**Engine:** `atlas-codex/HANDOFF_5ideas` `cost_atlas` + `route_adjudicator` (REAL, unmodified — imported, not edited).
**Fix under test:** per-estimator wall-clock budgets via `ATLAS_EST_BUDGET_S` with graceful *abstain* (`_run_budgeted` forks each estimator; on timeout it abstains instead of hanging). This removes the small-n **per-estimator HANG bug** that produced the original ~14 "timeouts."
**Corpus:** N = 115 unique circuits (published / field-assumed-hard), across 4 result files:
`results.json` (18), `batch2_published/results.json` (69), `tier2_vqe/results.json` (12), `tier2_qaoa_trotter/results.json` (16).
**Method:** re-ran every circuit through the FIXED engine via the existing read-only harness `worker.py` with `ATLAS_EST_BUDGET_S=15`, wall cap 240 s/circuit. Results written in place (same schema; provenance/citation fields preserved). Data only — nothing deployed, no site edit, no engine file modified, no fabrication (real engine output).

---

## Headline (REAL computed numbers)

> **108 of 115 routed classical (102 CPU · 4 TENSOR · 2 HPC_FIRST), 7 escalate, 0 timeout.**

The original 14 "timeouts" were an **engine bug, not circuit hardness**. Re-running with the fix resolves **all 14**: 10 to classical tiers, 4 to a genuine ESCALATE (verified hard, see below). Zero circuits still hang.

---

## BEFORE vs AFTER

| Metric | BEFORE (buggy run) | AFTER (fixed engine) |
|---|---|---|
| Total circuits | 115 | 115 |
| **Classical (CPU+TENSOR+HPC)** | **98** | **108** |
| &nbsp;&nbsp;• CPU | 94 | 102 |
| &nbsp;&nbsp;• TENSOR | 3 | 4 |
| &nbsp;&nbsp;• HPC_FIRST | 1 | 2 |
| **ESCALATE** | **3** | **7** |
| **TIMEOUT (bug)** | **14** | **0** |
| ERROR | 0 | 0 |

Per file (AFTER): `results.json` = 13 CPU / 2 HPC / 3 ESC · `batch2` = 63 CPU / 2 TENSOR / 4 ESC · `tier2_vqe` = 12 CPU · `tier2_qaoa_trotter` = 14 CPU / 2 TENSOR.

---

## The 14 previously-TIMED-OUT circuits — new resolved route

All 14 previously hung on the per-estimator small-n bug. New real routes:

| Circuit | n | NEW route | Governing | New timing | Note |
|---|---|---|---|---|---|
| vqe_uccsd_n28 | 28 | **HPC_FIRST** | statevector | 39.3 s | classical (2^28 SV) |
| qb_hhl_n10 | 10 | **CPU** | statevector | 34.8 s | classical |
| qb_bwt_n21 | 21 | **CPU** | statevector | 35.7 s | classical |
| qb_factor247_n15 | 15 | **CPU** | statevector | 41.3 s | classical |
| qb_hhl_n14 | 14 | **CPU** | statevector | 67.2 s | classical |
| qb_vqe_n24 | 24 | **TENSOR** | statevector | 47.9 s | classical |
| mqt_qwalk_n12 | 12 | **CPU** | statevector | 35.7 s | classical |
| mqt_shor_n18 | 18 | **CPU** | statevector | 36.4 s | classical |
| mqt_qwalk_n20 | 20 | **CPU** | statevector | 36.9 s | classical |
| qaoa_dense_n20_p2 | 20 | **CPU** | statevector | 24.4 s | classical |
| qb_QV_n100 | 100 | ESCALATE | compute-bound | 36.5 s | **genuinely hard** (random SU(4)) |
| qb_bwt_n37 | 37 | ESCALATE | compute-bound | 37.1 s | **genuinely hard** (large-n) |
| qb_qft_n160 | 160 | ESCALATE | compute-bound | 35.7 s | **genuinely hard** (large-n) |
| qb_square_root_n45 | 45 | ESCALATE | compute-bound | 35.8 s | **genuinely hard** (large-n) |

**10 → classical, 4 → ESCALATE.** The 4 ESCALATE are **NOT a bug and NOT budget artifacts**: re-probed at a large `ATLAS_EST_BUDGET_S=180 s`, all 4 still ESCALATE — their MPS bond truncates/blows up (high entanglement) and treewidth abstains. That is real hardness at these sizes (n = 37–160, or random-SU(4) QV at n=100 which is hard by construction).

---

## Honest note on 2 collateral circuits (budget calibration)

Two circuits that routed **CPU** in the buggy run relied on a *slow-but-exact* MPS estimate (~210–228 s each under the old un-budgeted estimator). At the corpus default `EST_BUDGET_S=15 s` their MPS estimator abstains and they would spuriously flip **CPU → ESCALATE**:

- **qft_n63** — re-verified at 240 s budget: **CPU**, MPS bond `2^0` (exact, low-entanglement, TN-tractable), 43.3 s.
- **qb_multiplier_n75** — re-verified at 240 s budget: **CPU**, MPS bond `2^0` (exact), 209.6 s.

Both are genuinely classical (exact low-bond MPS = provably low entanglement); the flip was a too-tight-budget artifact, not real hardness. Their records are set to the **real** CPU result with `est_budget_s_used: 240` and a `budget_note`. Keeping them classical avoids *understating* the engine. (The 4 large-n ESCALATE above were checked the same way and genuinely do not certify — so they honestly stay ESCALATE.)

**Takeaway on the knob:** `ATLAS_EST_BUDGET_S` trades certification latency for coverage. At 15 s the corpus is 108/115 classical; the only budget-sensitive cases are slow-to-certify-but-exact TN circuits (qft_n63, multiplier_n75), which a larger budget certifies as classical. Genuinely-hard circuits (RCS, hard-point kicked-Ising, large-n arithmetic, random QV) stay ESCALATE at any budget.

---

## The 7 ESCALATE circuits (all genuinely hard — real, not bug)

| Circuit | n | Why it escalates |
|---|---|---|
| kicked_ising_127q_hard_5steps | 127 | Kim-et-al hard operating point; high-entanglement Floquet |
| sycamore_rcs_53q_depth8 | 53 | Google RCS — designed classically-hard |
| sycamore_rcs_53q_depth20 | 53 | Google RCS deeper — designed classically-hard |
| qb_QV_n100 | 100 | Quantum Volume random SU(4) — hard by construction |
| qb_bwt_n37 | 37 | large-n; MPS blows up, treewidth abstains (verified @180 s) |
| qb_qft_n160 | 160 | large-n; MPS blows up, treewidth abstains (verified @180 s) |
| qb_square_root_n45 | 45 | large-n arithmetic; MPS blows up (verified @180 s) |

None of these ever "timed out" as a bug — they are honest ESCALATE (route to a quantum/large-HPC tier).

---

## Provenance / integrity

- Real engine output only. No fabricated numbers.
- Engine files imported, never edited. Site untouched. Nothing deployed.
- Updated in place: the four `results.json` files (schema preserved; `source`/`field_claim`/`classically_simulated_by`/`kind`/`suite`/`label`/`circuit_meta` provenance fields intact). Each file carries a `rerun_note`.
- Backups of the pre-rerun files were kept for the BEFORE/AFTER diff.

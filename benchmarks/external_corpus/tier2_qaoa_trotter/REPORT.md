# Tier-2 QAOA / Trotter Corpus — Atlas Real-Engine Routing

**What this is.** An offline research harness that runs Atlas's REAL engine
(`safe_parse` + `cost_atlas` + `route_adjudicator` from
`atlas-codex/HANDOFF_5ideas`) on circuits representative of the two most-cited
near-term "quantum advantage" use-cases: **QAOA / combinatorial optimization** and
**Trotterized Hamiltonian simulation**. For each circuit we record the actual
route, treewidth, MPS bond, T/magic count, the governing estimator, and the
single-estimator counterfactuals. Nothing was deployed; no route was fabricated;
the live web n-cap is untouched (`cost_atlas` is called directly, research-only).

**Circuit provenance (honest).** All circuits are **parametric and constructed** to
be representative of published QAOA / Hamiltonian-simulation workloads (standard
QAOA cost+mixer layers; standard TFIM / Heisenberg Trotter steps; random-ish
angles). They are **not** any specific paper's exact transpiled instance. Routing
depends on circuit **structure** (entanglement / treewidth / T-magic), which is
preserved regardless of the random rotation angles used.

## Corpus (16 circuits constructed; 15 ran, 1 timed out)

- **QAOA MaxCut** — per layer: `Rzz(2g)` on every graph edge, `Rx(2b)` on every
  qubit, repeated p times, from `|+>^n`.
  - **1D / sparse (path graph, low treewidth):** n=16 p1, n=20 p3, n=24 p2.
  - **Dense / random (Erdos-Renyi, high treewidth):** n=10 p1, n=16 p1, n=16 p3,
    n=20 p2 (**timed out**, see below), n=24 p2.
- **Trotterized Hamiltonian simulation** — a few steps each.
  - **TFIM** (`Rzz` bonds + `Rx` field): 1D line n=16 (4 steps), n=30 (5 steps);
    2D grid 3x4 n=12 (4), 4x5 n=20 (4).
  - **Heisenberg XXZ** (`Rxx`+`Ryy`+`Rzz` bonds + `Rz` field): 1D line n=20 (4),
    n=28 (5); 2D grid 4x4 n=16 (4), 4x6 n=24 (4).

## Results (REAL routes)

| circuit | type / structure | n | route | governing est. | treewidth | MPS bond | T | conf | treewidth-only baseline |
|---|---|---|---|---|---|---|---|---|---|
| qaoa_line_n16_p1 | QAOA / 1D line | 16 | **CPU** | MPS | 2^16 | 2^1 | 31 | high | CPU |
| qaoa_line_n20_p3 | QAOA / 1D line | 20 | **CPU** | MPS | 2^20 | 2^3 | 117 | high | CPU |
| qaoa_line_n24_p2 | QAOA / 1D line | 24 | **CPU** | MPS | 2^24 | 2^2 | 94 | high | CPU |
| qaoa_dense_n10_p1 | QAOA / dense ER | 10 | **CPU** | MPS | 2^11 | 2^5 | 33 | high | CPU |
| qaoa_dense_n16_p1 | QAOA / dense ER | 16 | **CPU** | statevector | 2^22 | 2^8 | 94 | medium | CPU |
| qaoa_dense_n16_p3 | QAOA / dense ER | 16 | **CPU** | statevector | 2^29 | 2^8 | 267 | medium | TENSOR |
| qaoa_dense_n20_p2 | QAOA / dense ER | 20 | **TIMEOUT** | — | — | — | — | — | — |
| qaoa_dense_n24_p2 | QAOA / dense ER | 24 | **TENSOR** | statevector | 2^43 | 2^6 (trunc) | 320 | medium | **ESCALATE** |
| trotter_tfim_line_n16_s4 | TFIM / 1D line | 16 | **CPU** | MPS | 2^17 | 2^3 | 124 | high | CPU |
| trotter_tfim_line_n30_s5 | TFIM / 1D line | 30 | **CPU** | MPS | 2^30 | 2^3.58 | 295 | high | **HPC_FIRST** |
| trotter_heis_line_n20_s4 | Heisenberg / 1D line | 20 | **CPU** | MPS | 2^20 | 2^4 | 308 | high | CPU |
| trotter_heis_line_n28_s5 | Heisenberg / 1D line | 28 | **CPU** | MPS | 2^28 | 2^5 | 545 | high | TENSOR |
| trotter_tfim_grid3x4_n12_s4 | TFIM / 2D grid | 12 | **CPU** | statevector | 2^18 | 2^6 | 116 | medium | CPU |
| trotter_tfim_grid4x5_n20_s4 | TFIM / 2D grid | 20 | **CPU** | statevector | 2^30 | 2^9.97 | 204 | medium | **HPC_FIRST** |
| trotter_heis_grid4x4_n16_s4 | Heisenberg / 2D grid | 16 | **CPU** | statevector | 2^20 | 2^8 | 352 | medium | CPU |
| trotter_heis_grid4x6_n24_s4 | Heisenberg / 2D grid | 24 | **TENSOR** | statevector | 2^31 | 2^6 (trunc) | 552 | medium | **HPC_FIRST** |

### Route distribution (REAL counts)

| tier | count |
|---|---|
| CPU (classical) | **13** |
| TENSOR (classical) | **2** |
| HPC_FIRST (classical) | 0 |
| ESCALATE | 0 |
| (timeout — no route) | 1 |

**15 / 15 circuits that ran routed to a CLASSICAL tier (13 CPU + 2 TENSOR). 0
ESCALATE.** One circuit (dense ER QAOA n=20 p=2) **timed out** at the 600 s budget —
see honest caveats.

## Honest finding

**Structure, not the "QAOA / Hamiltonian-simulation" label, drives the route — and
even drives *which estimator governs*.** The headline pattern, exactly as the data
shows it:

- **1D / area-law circuits (QAOA line, TFIM/Heisenberg line) -> CPU, governed by an
  exact MPS at tiny bond.** The MPS bond stays 2^1-2^5 *even at n=30* (TFIM line
  n=30 routes CPU at bond 2^3.58). Low entanglement, not small n, is the decisive
  signal: these stay on a laptop as n grows.
- **Dense-2D / dense-random circuits raise the MPS bond and treewidth sharply.**
  The same Trotter model on a 2D grid pushes the MPS bond to 2^6-2^10 (grid 4x5
  n=20: bond ~2^10 vs ~2^4 for the 1D chain), and dense QAOA pushes treewidth to
  2^29-2^43. Once the MPS bond saturates / truncates, MPS no longer certifies a
  cheap route, and the **exact statevector certificate** becomes the governing route
  — capping at **CPU** (n<=21) or **TENSOR** (22<=n<=27). That is why the two TENSOR
  routes are both n=24 dense/2D circuits.
- **Same QAOA depth, different graph -> different route.** QAOA at p=2: the n=24
  *line* routes CPU via MPS (bond 2^2), while the n=24 *dense* graph routes TENSOR
  via statevector (treewidth 2^43). Depth p is not the driver; graph structure is.

**This reinforces the multi-method thesis.** A treewidth-only router would have
**over-escalated 4 of the 15 circuits** — 1 to ESCALATE and 3 to HPC_FIRST (dense
QAOA n=24 -> ESCALATE on treewidth 2^43; TFIM line n=30, TFIM grid 4x5, Heisenberg
grid 4x6 -> HPC on treewidth alone). Atlas's real adjudicator routed all four to a
cheaper, *exact* tier instead (CPU via low-bond MPS for the 1D/area-law cases;
TENSOR via the exact statevector certificate for the n=24 dense/grid cases). The
extra estimators are what avoid the false alarm.

## Honest caveats (do not over-read)

1. **No ESCALATE, partly because of size.** Every circuit here is n<=30, inside the
   exact-statevector ceiling the adjudicator honors (n<=33). So "all classical" is
   partly the statevector certificate doing its job, not a claim that arbitrarily
   large 2D/dense instances are tractable. A genuinely 2D / dense / high-p instance
   at **n>33 with a truncated MPS** would have no cheap exact certificate and Atlas
   would route it to HPC_FIRST or ESCALATE — that regime is simply not in this
   constructed corpus.
2. **The one timeout is itself a signal.** Dense ER QAOA at n=20 p=2 did not finish
   the *treewidth / contraction-cost optimization* within 600 s — i.e. the classical
   cost analysis for that dense instance is itself near the edge. We record it
   honestly as TIMEOUT (no fabricated route) rather than dropping it.
3. **Constructed-representative, not paper-exact.** Angles are random; the result is
   scoped to the structural classes tested, not to any one published instance.

## Reproduce

```
.atlas-venv/bin/python benchmarks/external_corpus/tier2_qaoa_trotter/run_corpus.py
```

Outputs: `results.json` (per-circuit real metrics + route + structure label) and the
QASM under `tier2_qaoa_trotter/qasm/`. Engine: `HANDOFF_5ideas` real
`safe_parse` + `cost_atlas` + `route_adjudicator`.

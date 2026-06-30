# Tier-2 VQE / Quantum-Chemistry Corpus — Atlas Real-Engine Routing

**What this is.** An offline research harness that runs Atlas's REAL engine
(`safe_parse` + `cost_atlas` + `route_adjudicator` from
`atlas-codex/HANDOFF_5ideas`) on circuits representative of the quantum-chemistry /
VQE workloads vendors demo as "quantum chemistry on a quantum computer." For each
circuit we record the actual route, treewidth, MPS bond, T/magic count, and the
governing estimator. Nothing was deployed; no route was fabricated; the live web
n-cap is untouched (`cost_atlas` is called directly, research-only).

**Circuit provenance (honest).** All 12 circuits are **parametric and constructed**
to be representative of published VQE/chemistry workloads. They are **not** any
specific paper's or vendor's exact transpiled circuit. Routing depends on circuit
**structure** (entanglement / treewidth / T-magic), which is preserved regardless
of the random rotation angles used.

## Corpus (12 circuits)

- **Hardware-efficient ansatz (HEA)** — `ry`/`rz` on every qubit per layer + a CX
  entangling block. The canonical "QC chemistry demo" ansatz.
  - Linear entanglement (chain CX): n = 8, 12, 16, 20; plus one deep n=12 (reps=8).
  - Full / all-to-all entanglement (high-entanglement spread): n = 8, 12, 16, 20.
- **UCCSD-style** — Hartree-Fock reference + Trotterized single/double excitation
  operators (Jordan-Wigner CX-ladder + `rz` cores) at molecule-representative
  scales: H2 (~4 spin-orbitals), LiH (~12), BeH2 (~14).

## Results (REAL routes)

| circuit | n | route | governing est. | treewidth | MPS bond | T-count | conf |
|---|---|---|---|---|---|---|---|
| hea_linear_n8_d3 | 8 | **CPU** | MPS | 2^8 | 2^3 | 64 | high |
| hea_linear_n12_d3 | 12 | **CPU** | MPS | 2^12 | 2^3 | 96 | high |
| hea_linear_n16_d4 | 16 | **CPU** | MPS | 2^16 | 2^4 | 160 | high |
| hea_linear_n20_d4 | 20 | **CPU** | MPS | 2^20 | 2^4 | 200 | high |
| hea_linear_n12_d8 (deep) | 12 | **CPU** | statevector | 2^14 | 2^6 | 216 | medium |
| hea_full_n8_d3 | 8 | **CPU** | MPS | 2^12 | 2^3 | 64 | high |
| hea_full_n12_d3 | 12 | **CPU** | MPS | 2^17 | 2^3 | 96 | high |
| hea_full_n16_d3 | 16 | **CPU** | MPS | 2^20 | 2^3 | 128 | high |
| hea_full_n20_d2 | 20 | **CPU** | MPS | 2^24 | 2^2 | 120 | high |
| uccsd_h2_n4 | 4 | **CPU** | MPS | 2^5 | 2^0 | 3 | high |
| uccsd_lih_n12 | 12 | **CPU** | MPS | 2^13 | 2^0 | 12 | high |
| uccsd_beh2_n14 | 14 | **CPU** | MPS | 2^19 | 2^0 | 18 | high |

### Route distribution

| tier | count |
|---|---|
| CPU (classical) | **12** |
| TENSOR (classical) | 0 |
| HPC_FIRST (classical) | 0 |
| ESCALATE | 0 |

**12 / 12 routed to a CLASSICAL tier (all CPU). 0 ESCALATE.**

## Honest finding

Of the 12 representative VQE/quantum-chemistry circuits, **all 12 routed to a
classical tier** — and specifically to the cheapest one (CPU), not even TENSOR or
HPC. This supports the thesis "circuits marketed as needing a QC are often
classically tractable" — but only to the precise extent the routing shows it, with
two honest caveats:

1. **The governing estimator was MPS at a very low bond dimension** (2^0-2^6 across
   the corpus, including the all-to-all-entangled HEAs). The decisive factor is low
   **entanglement**, not just small n: random-angle ansatze at the depths actually
   marketed do not build the bond dimension that would force TENSOR/HPC. The
   all-to-all "high-entanglement" HEAs raise *treewidth* (up to 2^24) but their real
   MPS bond stays tiny, so MPS still governs and the route stays CPU. This is the
   meaningful structural signal, beyond the trivial "n is small."

2. **These sizes (n <= 20) are inside brute-force statevector reach anyway**
   (2^20 ~ 16 M amplitudes). So CPU routing here is unsurprising for the small cases
   on n alone; the low-bond MPS result is what indicates the *structure* would stay
   tractable (via MPS, not statevector) as n grows -- until entanglement saturates.

**What this does NOT claim.** It does not claim "a laptop beats a quantum computer."
A genuinely strongly-correlated molecule, a barren-plateau-avoiding deep ansatz, or
a hardware-optimized variational state at larger n could push MPS bond / treewidth
into TENSOR, HPC_FIRST, or ESCALATE -- and Atlas would route it there. The result is
scoped to the **constructed, demo-representative circuits at the scales/depths
tested**: at those, Atlas's real engine finds them classically tractable.

## Reproduce

```
.atlas-venv/bin/python benchmarks/external_corpus/tier2_vqe/gen_and_run.py
```

Outputs: `results.json` (per-circuit real metrics + route + provenance) and the
QASM under `tier2_vqe/qasm/`. Engine: `HANDOFF_5ideas` real
`safe_parse` + `cost_atlas` + `route_adjudicator`.

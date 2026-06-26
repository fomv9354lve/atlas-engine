# Scaled Validation Report

Corpus size: **800** circuits (**800** oracle-certified, **0** uncertified lower/upper-bound only).

`expected_route` here is **measured**, not hand-assigned: it is the cheapest route certified by an exact measurement (Stim Clifford / non-truncated MPS / exact treewidth). Accuracy on the certified subset is therefore a non-circular test.

## Stratification

| Family | n | | n-qubits | n | | T-density | n |
|---|---:|---|---:|---:|---|---|---:|
| all_to_all_sparse | 80 | | 8 | 128 | clifford | 201 |
| dense_core | 120 | | 12 | 152 | high | 200 |
| grid | 104 | | 16 | 144 | low | 199 |
| heavy_hex | 128 | | 20 | 136 | med | 200 |
| ladder | 120 | | 24 | 128 |  |  |
| line | 128 | | 30 | 112 |  |  |
| star | 120 | |  |  |  |  |

## Route Accuracy vs Measured Oracle (certified subset)

| Method | Accuracy | Mean ordinal error |
|---|---:|---:|
| atlas | 0.991 | 0.009 |
| treewidth_only | 0.724 | 0.475 |
| mps_only | 0.836 | 0.164 |
| magic_only | 0.331 | 0.749 |

## Route Accuracy vs Oracle (full corpus, incl. uncertified bound)

| Method | Accuracy | Mean ordinal error |
|---|---:|---:|
| atlas | 0.991 | 0.009 |
| treewidth_only | 0.724 | 0.475 |
| mps_only | 0.836 | 0.164 |
| magic_only | 0.331 | 0.749 |

## Failure Modes (certified subset)

- Atlas false-safety (said cheap, oracle escalates): **0**
- Atlas false-alarm (escalated, oracle cheap): **0**
- Treewidth-only false-alarm: **166**
- MPS-only false-safety: **16**

These are the operationally costly errors: a false-safety wastes a doomed laptop run; a false-alarm wastes HPC/QPU budget on a circuit a laptop could finish. Atlas is designed to minimise both by adjudicating across estimators rather than trusting one.

## Uncertified Tail: where Atlas earns its keep

The oracle cannot certify a cheap route for **0** circuits (**0** have a truncated MPS lower bound). This tail is excluded from certified accuracy precisely because no exact route exists -- but it is where a single-estimator reading is most dangerous.

- mps-only calls **0** truncated circuits cheap (trusting a lower bound as if it certified safety).
- Atlas escalates **0** of the truncated circuits (invalidating MPS as a lower bound).
- **0** circuits are latent mps-only false-safety that Atlas explicitly guards against. This is the operational value that the certified-subset accuracy (which favours mps-only by construction) cannot show.

## Score Calibration (16B): empirical percentile mapping

The 0-100 index is **not** a probability; it is mapped here to its empirical percentile in the corpus.

| Percentile | Score threshold |
|---:|---:|
| 10 | 20.0 |
| 25 | 26.0 |
| 50 | 32.0 |
| 75 | 42.0 |
| 90 | 42.0 |
| 95 | 70.0 |
| 99 | 100.0 |

Score vs measured `union_cost_log2`: Pearson 0.735, Spearman 0.829, Kendall 0.607.

## Confidence Reliability (16C)

Computed on the 800-circuit certified subset: does the adjudicator's confidence band predict actually matching the measured oracle?

| Confidence band | n | Empirical accuracy | Mean confidence |
|---|---:|---:|---:|
| low | 7 | 0.000 | 0.340 |
| medium | 172 | 1.000 | 0.511 |
| high | 621 | 1.000 | 0.886 |

A reliable confidence model has empirical accuracy rising with the confidence band, and the high band's accuracy close to its mean confidence. Gaps here are the calibration debt to close before publishing confidence as anything stronger than a declared heuristic.

## Honest Limitations

1. The oracle certifies routes only where an exact measurement exists; the uncertified tail (truncated MPS + greedy treewidth) is reported separately and never folded into certified accuracy.
2. Route thresholds are fixed cost-model constants, not fitted to wall-clock on a target machine.
3. This corpus is synthetic-family stratified; real-workload circuits remain future work.

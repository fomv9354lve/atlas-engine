"""Sycamore-scale Random Circuit Sampling (RCS) generator, via cirq's official
supremacy-circuit generator (the ABCDCDAB pattern and the {sqrt(X), sqrt(Y),
sqrt(W)} single-qubit set of Arute et al., Nature 574, 505 (2019), "Quantum
supremacy using a programmable superconducting processor").

HONESTY: this uses cirq's `random_rotations_between_grid_interaction_layers_circuit`
(the same routine that produced the supremacy circuits) on a 2D grid of Sycamore
SCALE (~53 qubits). The two-qubit entangler is exported as CZ (atlas parses CZ;
Google's hardware gate was fSim/iSWAP-like, but the classical-hardness driver for
routing is the 2D-grid treewidth, which CZ on the same pattern preserves). This is
NOT Google's exact device coordinates nor their released amplitudes -- it is a
faithful methodological reconstruction of the RCS family at Sycamore scale.

RCS at 53q depth-20 was the frontier "quantum supremacy" claim; later classically
reproduced/spoofed by tensor-network methods (Pan, Chen, Zhang, PRL 129, 090502
(2022); Liu et al., ACM Gordon Bell 2021; Kalachev et al. 2021). Atlas routing a
shallow RCS to TENSOR and a deep one to HPC/ESCALATE is the honest outcome -- it
genuinely WAS (and at depth, remains) high-treewidth.
"""
from __future__ import annotations
import cirq

N_QUBITS = 53


def _sycamore_scale_qubits(n=N_QUBITS):
    """A contiguous 2D grid patch of n qubits (Sycamore scale). Not the exact
    Sycamore device graph (that needs cirq_google), but a 2D grid whose treewidth
    grows like the Sycamore lattice -- which is what governs the classical route."""
    qs = []
    rows, cols = 6, 9  # 54-cell grid; drop one to hit 53 (Sycamore had 53 working qubits)
    for r in range(rows):
        for c in range(cols):
            qs.append(cirq.GridQubit(r, c))
    return qs[:n]


def rcs_qasm(depth: int, seed: int = 0) -> str:
    qubits = _sycamore_scale_qubits()
    circuit = cirq.experiments.random_rotations_between_grid_interaction_layers_circuit(
        qubits=qubits,
        depth=depth,
        two_qubit_op_factory=lambda a, b, _: cirq.CZ(a, b),  # atlas-parseable; preserves grid treewidth
        seed=seed,
    )
    # cirq needs LineQubit/named for QASM; map grid->line
    qmap = {q: cirq.LineQubit(i) for i, q in enumerate(sorted(qubits))}
    circuit = circuit.transform_qubits(qmap)
    return circuit.to_qasm()


if __name__ == "__main__":
    import sys
    d = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(rcs_qasm(d)[:400])

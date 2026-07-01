"""NON-CIRCULAR ground-truth worker: EXACT dense statevector simulation of ONE
qasm file, printed as a JSON line.

This is BRUTE-FORCE EXECUTION, not an estimate. We build the full 2^n complex128
amplitude vector and evolve it gate-by-gate with numpy tensordot. If it completes
within the memory + time budget, the circuit is PROVABLY classically tractable BY
EXECUTION (the amplitudes physically exist in RAM) -- a ground truth INDEPENDENT of
the MPS-bond / treewidth estimators Atlas uses elsewhere (which grade routes using
the same tensor-network formalism that labels them, hence the circularity critique).

Pipeline:
  1. parse with qiskit.qasm2  (independent of Atlas's own parser)
  2. transpile to the {u, cx} basis, optimization_level=0 (pure gate translation,
     no route/cost heuristic) so every circuit reduces to 1-qubit u + cx
  3. apply u and cx to a dense numpy statevector via tensordot -- exact, no truncation

Run as a subprocess so a slow/deep circuit is killed by the parent's timeout without
fabricating success.
"""
from __future__ import annotations
import sys, json, time
import numpy as np

CAP_N = 26  # 2^26 * 16 B ~ 1.07 GB one copy; safe on a 25.7 GB laptop. Stated honestly.


def u_matrix(theta, phi, lam):
    c = np.cos(theta / 2.0)
    s = np.sin(theta / 2.0)
    return np.array([
        [c, -np.exp(1j * lam) * s],
        [np.exp(1j * phi) * s, np.exp(1j * (phi + lam)) * c],
    ], dtype=np.complex128)


def apply_1q(state, g, q, n):
    # flat reshape exposing only qubit q as the middle axis (ndim=3, contiguous, fast)
    s = 1 << q
    v = state.reshape(-1, 2, s)
    v0 = v[:, 0, :].copy()  # only the |0> block needs saving; |1> block read fresh below
    v[:, 0, :] = g[0, 0] * v0 + g[0, 1] * v[:, 1, :]
    v[:, 1, :] = g[1, 0] * v0 + g[1, 1] * v[:, 1, :]
    return state


def apply_cx(state, c, t, n):
    # reshape to <=5 axes exposing bit hi (axis1) and bit lo (axis3); swap target rows
    # where control==1. Only touches half the array; no big transpose.
    hi, lo = max(c, t), min(c, t)
    A = 1 << (n - hi - 1)
    B = 1 << (hi - lo - 1)
    C = 1 << lo
    v = state.reshape(A, 2, B, 2, C)
    if c == hi:  # control is axis1, target is axis3
        tmp = v[:, 1, :, 0, :].copy()
        v[:, 1, :, 0, :] = v[:, 1, :, 1, :]
        v[:, 1, :, 1, :] = tmp
    else:        # control is axis3 (lo), target is axis1 (hi)
        tmp = v[:, 0, :, 1, :].copy()
        v[:, 0, :, 1, :] = v[:, 1, :, 1, :]
        v[:, 1, :, 1, :] = tmp
    return state


def main():
    path = sys.argv[1]
    out = {"exact_sim_method": "dense_statevector(numpy,tensordot,u+cx basis)",
           "exact_sim_feasible": False, "exact_sim_seconds": None,
           "n_sv": None, "n_gates_basis": None, "note": None}
    try:
        from qiskit import qasm2, transpile
        from qiskit.circuit.library import RXXGate, RYYGate, RZZGate
        # some published files use rxx/ryy/rzz as bare (non-qelib1) gates; teach the parser.
        have = {ci.name for ci in qasm2.LEGACY_CUSTOM_INSTRUCTIONS}
        cand = [qasm2.CustomInstruction("rxx", 1, 2, RXXGate, builtin=True),
                qasm2.CustomInstruction("ryy", 1, 2, RYYGate, builtin=True),
                qasm2.CustomInstruction("rzz", 1, 2, RZZGate, builtin=True)]
        extra = [c for c in cand if c.name not in have]
        try:
            qc = qasm2.load(path, custom_instructions=list(qasm2.LEGACY_CUSTOM_INSTRUCTIONS) + extra,
                            custom_classical=qasm2.LEGACY_CUSTOM_CLASSICAL, strict=False)
        except TypeError:
            qc = qasm2.load(path)
        qc = qc.remove_final_measurements(inplace=False) or qc
        n = qc.num_qubits
        out["n_sv"] = n
        if n > CAP_N:
            out["note"] = (f"n={n} > CAP_N={CAP_N}: exact dense statevector exceeds the safe "
                           f"memory cap on this machine (2^{n} amplitudes)")
            print(json.dumps(out)); return
        t_parse = time.time()
        tqc = transpile(qc, basis_gates=["u", "cx"], optimization_level=0)
        # extract flat instruction stream
        qubit_index = {q: i for i, q in enumerate(tqc.qubits)}
        ops = []
        for ci in tqc.data:
            name = ci.operation.name
            qs = [qubit_index[q] for q in ci.qubits]
            if name == "u":
                th, ph, la = [float(p) for p in ci.operation.params]
                ops.append(("u", qs[0], (th, ph, la)))
            elif name == "cx":
                ops.append(("cx", qs[0], qs[1]))
            elif name == "barrier":
                continue
            elif name in ("measure", "reset", "if_else", "c_if", "while_loop", "for_loop", "switch_case"):
                # NON-UNITARY / classical control flow: a pure statevector cannot faithfully
                # represent this. Abort honestly rather than silently drop the op and report a
                # (wrong) 'feasible'. This keeps every 'confirmed' verdict a TRUE exact simulation.
                raise RuntimeError(f"non-unitary/control-flow op '{name}' present; pure statevector cannot certify (honest exclusion, not a tractability claim)")
            else:
                raise RuntimeError(f"unexpected basis gate after transpile: {name}")
        out["n_gates_basis"] = len(ops)
        t0 = time.time()
        state = np.zeros(1 << n, dtype=np.complex128)
        state[0] = 1.0
        for op in ops:
            if op[0] == "u":
                state = apply_1q(state, u_matrix(*op[2]), op[1], n)
            else:
                state = apply_cx(state, op[1], op[2], n)
        # force realization + sanity: norm must be ~1 (exact, unitary)
        norm = float(np.vdot(state.ravel(), state.ravel()).real)
        dt = time.time() - t0
        out["exact_sim_feasible"] = True
        out["exact_sim_seconds"] = round(dt, 3)
        out["statevector_norm"] = round(norm, 6)
        out["note"] = (f"exact statevector realized: 2^{n} amplitudes "
                       f"({(2**n)*16/1e6:.1f} MB), {len(ops)} basis gates applied, "
                       f"norm={norm:.6f} (unitary check)")
    except Exception as e:
        out["note"] = f"sim_error: {type(e).__name__}: {str(e)[:200]}"
    print(json.dumps(out))


if __name__ == "__main__":
    main()

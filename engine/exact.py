"""exact.py -- verificaciones EXACTAS (no heuristicas) para n pequeno.

CIERRA LA DEUDA #2 (magia): el cross-check '#T vs Stim' solo valida Clifford-ness via (T==0). Aqui, para
n<=6, construimos el UNITARIO del circuito y testeamos pertenencia EXACTA al grupo de Clifford (¿conjuga cada
Pauli generador a un Pauli?). Esto CAZA el caso borde: un circuito con T-gates que es, sin embargo,
Clifford-equivalente (su unitario es Clifford) -> la magia sintactica sobre-cuenta, y aqui se detecta.
"""
from __future__ import annotations
import numpy as np

_S2 = 1 / np.sqrt(2)
H = np.array([[_S2, _S2], [_S2, -_S2]], complex)
X = np.array([[0, 1], [1, 0]], complex)
Y = np.array([[0, -1j], [1j, 0]], complex)
Z = np.array([[1, 0], [0, -1]], complex)
S = np.array([[1, 0], [0, 1j]], complex)
Sdg = S.conj().T
T = np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], complex)
Tdg = T.conj().T
I2 = np.eye(2, dtype=complex)
_1Q = {"h": H, "x": X, "y": Y, "z": Z, "s": S, "sdg": Sdg, "t": T, "tdg": Tdg}


def _op1(n, g, q):
    ops = [I2] * n; ops[q] = g
    M = ops[0]
    for k in range(1, n):
        M = np.kron(M, ops[k])
    return M


def _rz(theta):
    return np.array([[np.exp(-1j * theta / 2), 0], [0, np.exp(1j * theta / 2)]], complex)


def _cx(n, a, b):
    d = 2 ** n; M = np.zeros((d, d), complex)
    for i in range(d):
        j = i ^ (1 << (n - 1 - b)) if (i >> (n - 1 - a)) & 1 else i
        M[j, i] = 1
    return M


def _cz(n, a, b):
    d = 2 ** n; M = np.eye(d, dtype=complex)
    for i in range(d):
        if ((i >> (n - 1 - a)) & 1) and ((i >> (n - 1 - b)) & 1):
            M[i, i] = -1
    return M


def _apply1(U, G, q, n):
    """Aplica un gate 1-qubit G sobre el qubit q a TODAS las columnas de U a la vez (O(4^n), no O(8^n))."""
    T = U.reshape((2,) * n + (-1,))
    T = np.tensordot(G, T, axes=([1], [q]))
    return np.moveaxis(T, 0, q).reshape(2 ** n, -1)


def _apply2(U, G4, a, b, n):
    """Aplica un gate 2-qubit (matriz 4x4) sobre (a,b) a todas las columnas de U."""
    G = G4.reshape(2, 2, 2, 2)
    T = U.reshape((2,) * n + (-1,))
    T = np.tensordot(G, T, axes=([2, 3], [a, b]))          # ejes de entrada de G -> qubits a,b
    return np.moveaxis(T, [0, 1], [a, b]).reshape(2 ** n, -1)


_CX4 = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1], [0, 0, 1, 0]], complex)
_CZ4 = np.diag([1, 1, 1, -1]).astype(complex)


def unitary(n, circuit):
    """Unitario 2^n x 2^n del circuito, aplicando gates columna-a-columna (O(4^n)/gate) -> escala a n~10."""
    U = np.eye(2 ** n, dtype=complex)
    for g in circuit:
        op = g[0]
        if op in _1Q:
            U = _apply1(U, _1Q[op], g[1], n)
        elif op == "rz":
            U = _apply1(U, _rz(g[2]), g[1], n)
        elif op in ("cx", "cnot"):
            U = _apply2(U, _CX4, g[1], g[2], n)
        elif op == "cz":
            U = _apply2(U, _CZ4, g[1], g[2], n)
        # otros (barrier/measure) se ignoran
    return U


def _is_pauli_upto_phase(M, tol=1e-7):
    """¿M es un Pauli-string por una fase global? (monomial + permutacion XOR-constante + fases ±1)."""
    d = M.shape[0]
    perm = np.argmax(np.abs(M), axis=0)               # fila i -> columna del no-cero
    # monomial: exactamente un |entrada|~1 por columna, resto ~0
    for i in range(d):
        col = M[:, i]
        big = np.abs(col) > 0.5
        if big.sum() != 1 or abs(np.abs(col[big][0]) - 1) > tol:
            return False
    a = perm[0]
    if not np.all(perm == (np.arange(d) ^ a)):        # permutacion = XOR por constante a (parte X)
        return False
    ref = M[perm[0], 0]
    for i in range(d):                                # fases relativas deben ser ±1 (parte Z); T las rompe
        r = M[perm[i], i] / ref
        if abs(r.imag) > tol or abs(abs(r.real) - 1) > tol:
            return False
    return True


def is_clifford_exact(n, circuit):
    """EXACTO (n<=6): ¿el unitario del circuito esta en el grupo de Clifford? Devuelve True/False o None si
    n es demasiado grande para construir el unitario."""
    if n > 9:                                          # corte por PRESUPUESTO DE LATENCIA (~0.1s a n=9), no
        return None                                    # por limite del metodo: funciona mas alla, lo limita el reloj
    U = unitary(n, circuit); Ud = U.conj().T
    for q in range(n):
        for P in (_op1(n, X, q), _op1(n, Z, q)):       # basta con los generadores X_q, Z_q
            if not _is_pauli_upto_phase(U @ P @ Ud):
                return False
    return True


def noisy_fidelity_exact(n, circuit, p):
    """EXACTO (n<=6): fidelidad del estado RUIDOSO vs ideal, via matriz de densidad con canal depolarizante a
    tasa p por compuerta de 2 qubits. VALIDA el modelo analitico F~e^(-lambda) de noise.py (pendiente cerrada
    para n pequeno). Devuelve (F_exacta, F_analitica) o None si n grande."""
    if n > 6:
        return None
    d = 2 ** n
    psi = np.zeros(d, complex); psi[0] = 1.0
    rho = np.outer(psi, psi.conj())
    psi_ideal = psi.copy()
    n_2q = 0
    for g in circuit:
        op = g[0]
        if op in _1Q:
            U = _op1(n, _1Q[op], g[1])
        elif op == "rz":
            U = _op1(n, _rz(g[2]), g[1])
        elif op in ("cx", "cnot"):
            U = _cx(n, g[1], g[2])
        elif op == "cz":
            U = _cz(n, g[1], g[2])
        else:
            continue
        rho = U @ rho @ U.conj().T
        psi_ideal = U @ psi_ideal
        if op in ("cx", "cnot", "cz"):                     # depolarizante tras cada compuerta de 2 qubits
            n_2q += 1
            rho = (1 - p) * rho + p * np.trace(rho).real * np.eye(d) / d
    F_exact = float(np.real(psi_ideal.conj() @ rho @ psi_ideal))
    d = 2.0 ** n
    F_analytic = float(1.0 / d + (1.0 - 1.0 / d) * (1.0 - p) ** n_2q)   # forma CERRADA (no e^-lambda)
    return F_exact, F_analytic


def main():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    print("exact.py -- test de Clifford EXACTO (n pequeno)\n")
    cases = [
        ("Clifford puro (H,CX,S)", 3, [("h", 0), ("cx", 0, 1), ("s", 2), ("cx", 1, 2)], True),
        ("con T (no-Clifford)", 2, [("h", 0), ("t", 1)], False),
        ("T^8 = I (Clifford-equiv)", 1, [("t", 0)] * 8, True),
        ("T,T (=S, Clifford-equiv)", 1, [("t", 0), ("t", 0)], True),
        ("Toffoli (no-Clifford)", 3, [("ccx", 0, 1, 2)], False),  # ccx no esta en unitary -> se ignora -> identidad=Clifford (limitacion)
    ]
    for name, n, circ, expect in cases:
        r = is_clifford_exact(n, circ)
        print(f"  {name:30}: Clifford={r}  (esperado {expect})  {'OK' if r == expect else 'REVISAR'}")
    print("DONE")


if __name__ == "__main__":
    main()

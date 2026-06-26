"""Invariantes FISICOS analiticos (F-1 del audit) — auto-contenido, NO toca el motor de dureza.

Mientras el resto de Atlas mide COSTE computacional (magic / MPS / treewidth), este modulo evalua un
OBSERVABLE FISICO real — la entropia de entrelazamiento bipartita von Neumann del estado de salida — y la
contrasta contra valores ANALITICOS conocidos (Bell = ln2, GHZ = ln2, producto = 0). Asi "ground-truth"
incluye fisica verificable, no solo routing de coste.

Statevector exacto en numpy para n pequeno (cap n<=14). Convencion: el qubit k es el eje k del tensor.
"""
import math
import numpy as np

_SQ = 1.0 / math.sqrt(2.0)
_G1 = {
    "h":   np.array([[_SQ, _SQ], [_SQ, -_SQ]], dtype=complex),
    "x":   np.array([[0, 1], [1, 0]], dtype=complex),
    "y":   np.array([[0, -1j], [1j, 0]], dtype=complex),
    "z":   np.array([[1, 0], [0, -1]], dtype=complex),
    "s":   np.array([[1, 0], [0, 1j]], dtype=complex),
    "sdg": np.array([[1, 0], [0, -1j]], dtype=complex),
    "t":   np.array([[1, 0], [0, np.exp(1j * math.pi / 4)]], dtype=complex),
    "tdg": np.array([[1, 0], [0, np.exp(-1j * math.pi / 4)]], dtype=complex),
    "sx":  0.5 * np.array([[1 + 1j, 1 - 1j], [1 - 1j, 1 + 1j]], dtype=complex),
}
INVARIANT_CAP = 14   # 2^14 = 16384 amplitudes; SVD de 2^7 x 2^7 — instantaneo


def _apply1(psi, n, q, U):
    psi = psi.reshape([2] * n)
    psi = np.tensordot(U, psi, axes=([1], [q]))
    psi = np.moveaxis(psi, 0, q)
    return psi.reshape(-1)


def _apply_ctrl(psi, n, c, t, U):
    psi = psi.reshape([2] * n)
    sl = [slice(None)] * n
    sl[c] = 1                                   # solo el subespacio con el control en |1>
    sub = psi[tuple(sl)]
    ta = t - 1 if t > c else t                  # eje de t tras quitar el eje c
    sub = np.tensordot(U, sub, axes=([1], [ta]))
    sub = np.moveaxis(sub, 0, ta)
    psi[tuple(sl)] = sub
    return psi.reshape(-1)


def _swap(psi, n, a, b):
    psi = psi.reshape([2] * n)
    psi = np.swapaxes(psi, a, b)
    return psi.reshape(-1)


def statevector(n, circuit):
    """Statevector exacto. circuit: tuplas del parser de atlas (h/x/y/z/s/sdg/t/tdg/sx q), (cx/cz/swap a b).
    Gates fuera de ese set se ignoran (devuelve tambien la lista de ops omitidos)."""
    psi = np.zeros(2 ** n, dtype=complex)
    psi[0] = 1.0
    skipped = set()
    for g in circuit:
        op = g[0]
        if op in _G1:
            psi = _apply1(psi, n, g[1], _G1[op])
        elif op in ("cx", "cnot"):
            psi = _apply_ctrl(psi, n, g[1], g[2], _G1["x"])
        elif op == "cz":
            psi = _apply_ctrl(psi, n, g[1], g[2], _G1["z"])
        elif op == "swap":
            psi = _swap(psi, n, g[1], g[2])
        else:
            skipped.add(op)
    return psi, skipped


def entanglement_entropy(psi, n, cut=None):
    """Entropia von Neumann (en nats) de la biparticion [0..cut) | [cut..n)."""
    if cut is None:
        cut = n // 2
    cut = max(1, min(n - 1, cut))
    M = psi.reshape(2 ** cut, 2 ** (n - cut))
    s = np.linalg.svd(M, compute_uv=False)
    p = s ** 2
    p = p[p > 1e-12]
    return float(-np.sum(p * np.log(p)))


def circuit_entropy(n, circuit, cut=None):
    """Entropia de entrelazamiento del estado de salida, o None si n excede el cap o quedaron gates sin soportar."""
    if n < 2 or n > INVARIANT_CAP:
        return None, None
    psi, skipped = statevector(n, circuit)
    if skipped:
        return None, sorted(skipped)
    return round(entanglement_entropy(psi, n, cut), 4), None


def _entropy_subset(psi, n, subset):
    """S von Neumann de una biparticion ARBITRARIA (subset de qubits | resto). No requiere orden contiguo."""
    k = len(subset)
    t = psi.reshape([2] * n)
    rest = [q for q in range(n) if q not in subset]
    t = np.transpose(t, subset + rest)          # mueve los qubits del subset al frente
    M = t.reshape(2 ** k, 2 ** (n - k))
    s = np.linalg.svd(M, compute_uv=False)
    p = s ** 2; p = p[p > 1e-12]
    return float(-np.sum(p * np.log(p)))


def entanglement_profile(n, circuit, n_random=24, seed=7):
    """Defensa anti S-spoofing / MPS-camouflage: S en TODOS los cortes contiguos [1..n-1] (orden
    indice) MAS biparticiones ARBITRARIAS muestreadas (cierra el vector de permutacion de qubits).

    Returns (dict, skipped): s_half, s_max_contig, s_max_any, argmax_cut, asymmetry (s_max_any - s_half),
    permutation_camouflage (True si una biparticion no-contigua supera el max contiguo). None si n>cap.
    """
    if n < 2 or n > INVARIANT_CAP:
        return None, None
    psi, skipped = statevector(n, circuit)
    if skipped:
        return None, sorted(skipped)
    prof = [round(entanglement_entropy(psi, n, c), 4) for c in range(1, n)]
    s_half = prof[n // 2 - 1]
    s_max_contig = max(prof)
    # biparticiones arbitrarias (balanceadas) — captura entrelazamiento escondido por permutacion.
    # EXHAUSTIVO para n chico (todas las C(n, n//2)); muestreado arriba. Cierra el vector completo a n<=12.
    import itertools as _it
    import math as _m
    half = n // 2
    s_any = s_max_contig
    n_combos = _m.comb(n, half)
    exhaustive = n_combos <= 1024            # n<=12 -> exhaustivo (C(12,6)=924)
    if exhaustive:
        for sub in _it.combinations(range(n), half):
            s_any = max(s_any, _entropy_subset(psi, n, list(sub)))
    else:
        import random as _r
        rng = _r.Random(seed); seen = set()
        for _ in range(min(n_random, n_combos)):
            sub = tuple(sorted(rng.sample(range(n), half)))
            if sub in seen:
                continue
            seen.add(sub)
            s_any = max(s_any, _entropy_subset(psi, n, list(sub)))
    s_max_any = round(s_any, 4)
    return {"s_half": s_half, "s_max_contig": s_max_contig, "s_max_any": s_max_any,
            "s_max": s_max_any,  # compat: el max global
            "argmax_cut": prof.index(s_max_contig) + 1,
            "asymmetry": round(s_max_any - s_half, 4),
            "permutation_camouflage": bool(s_max_any > s_max_contig + 0.3),
            "bipartition_coverage": ("exhaustive" if exhaustive else "sampled_%d" % n_random),
            "profile": prof}, None


_PAULI = [np.eye(2, dtype=complex), _G1["x"], _G1["y"], _G1["z"]]
MAGIC_CAP = 6   # M2 enumera 4^n Paulis: n=6 -> 4096, instantaneo; arriba se omite

def stabilizer_renyi(psi, n):
    """Entropia estabilizadora 2-Renyi M2 (Leone-Oliviero-Hamma 2022): mide la MAGIA del ESTADO, no de la
    sintaxis. M2=0 sii el estado es estabilizador (Clifford); M2>0 lo certifica no-Clifford. Es independiente
    del conteo de T-gates -> cross-validation FISICA real (no la redundancia syntactica de tcount_vs_stim)."""
    if n < 1 or n > MAGIC_CAP:
        return None
    total = 0.0
    for idx in range(4 ** n):
        Pp = psi.copy(); k = idx
        for q in range(n):
            p = k & 3; k >>= 2
            if p:
                Pp = _apply1(Pp, n, q, _PAULI[p])
        exp = np.vdot(psi, Pp).real
        total += exp ** 4
    return float(-math.log2(total / (2 ** n)))


def magic_cross_check(n, circuit, t_count):
    """Compara la magia medida del ESTADO (M2) con el conteo de T-gates de la SINTAXIS. Detecta, por ejemplo,
    T-gates que se cancelan (T^8=I): sintaxis veria T>0 pero el estado tendria M2=0. Devuelve dict o None."""
    if n < 1 or n > MAGIC_CAP:
        return None
    psi, skipped = statevector(n, circuit)
    if skipped:
        return None
    m2 = stabilizer_renyi(psi, n)
    state_magic = m2 is not None and m2 > 1e-6
    synt_magic = (t_count or 0) > 0
    return {"M2": round(m2, 4), "state_is_magic": state_magic, "syntax_T": int(t_count or 0),
            "consistent": state_magic == synt_magic}


def selftest():
    """Verifica el observable contra valores ANALITICOS conocidos. Esto es ground-truth FISICO, no de coste."""
    cases = [
        ("Bell |Phi+>", 2, [("h", 0), ("cx", 0, 1)], 1, math.log(2)),
        ("GHZ_3",       3, [("h", 0), ("cx", 0, 1), ("cx", 1, 2)], 1, math.log(2)),
        ("producto HxH", 2, [("h", 0), ("h", 1)], 1, 0.0),
        ("W-ish (S q)", 2, [("h", 0), ("cx", 0, 1), ("t", 1)], 1, math.log(2)),  # T local no cambia la entropia
    ]
    checks = []
    for name, n, circ, cut, expected in cases:
        psi, _ = statevector(n, circ)
        got = entanglement_entropy(psi, n, cut)
        checks.append({"name": name, "got": round(got, 4), "expected": round(expected, 4),
                       "ok": abs(got - expected) < 1e-6})
    # MAGIA medida del ESTADO (M2): Clifford -> 0, no-Clifford -> >0. Independiente del conteo syntactico.
    magic_cases = [
        ("Clifford (Bell) M2=0", [("h", 0), ("cx", 0, 1)], 2, False),
        ("T-doped (T q0) M2>0",  [("h", 0), ("t", 0)], 1, True),
        ("T^8=I cancela M2=0",   [("t", 0)] * 8, 1, False),     # 8 T = identidad -> estado estabilizador
    ]
    magic = []
    for name, circ, n, want_magic in magic_cases:
        m2 = stabilizer_renyi(statevector(n, circ)[0], n)
        is_magic = m2 > 1e-6
        magic.append({"name": name, "M2": round(m2, 4), "ok": is_magic == want_magic})
    return {"ln2": round(math.log(2), 4), "checks": checks, "magic": magic,
            "all_ok": all(c["ok"] for c in checks) and all(m["ok"] for m in magic)}


if __name__ == "__main__":
    import json
    print(json.dumps(selftest(), indent=2, ensure_ascii=False))

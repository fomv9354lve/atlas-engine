"""Sparse-Pauli-dynamics (Pauli-path / operator-spread) estimator -- self-contained, arsenal-free.

WHAT THIS IS. A cheap, n-INDEPENDENT classical-tractability axis for the PUBLIC engine. Given a circuit and a
LOCAL observable O, we propagate O BACKWARD through the gates in the Heisenberg picture -- O -> g^dag O g for
each gate g from LAST to FIRST -- tracking the number of Pauli strings the observable spreads into. Clifford
gates map one Pauli to one Pauli (no growth); non-Clifford Z-rotations (t/tdg/rz) BRANCH a Pauli into two.
`peak_spread` is the max #terms over the whole propagation; `spread_log2 = log2(peak_spread)`. If the term
count ever exceeds `max_terms`, we ABORT (O(budget) work, not 2^t) and report the axis as saturated.

WHY IT MATTERS. This is bounded by the observable's LIGHTCONE and the number of T-gates inside it -- NOT by n.
So it resolves in <100ms for n=20,30,40 shallow-local circuits, exactly the regime where the private arsenal's
ARSENAL_CAP=14 (a 2^n fold) returned None. A local observable of a shallow/structured circuit stays cheap
(low spread_log2) even at high total magic; a deep scrambling circuit saturates (aborts) -- that classification
IS the tractability signal.

HONEST SCOPE. We classify the cheap/hard boundary at low cost; we do NOT solve hard points cheaply (the abort
is the wall being detected, not paid). Branching cost grows with the number of T-gates in the observable's
lightcone, not with n. Unknown gates are treated CONSERVATIVELY (spread_log2 = n, i.e. "spreads fully, no
cheap route") -- we NEVER understate hardness.

Pauli encoding: per qubit (x,z) in {(0,0)=I,(1,0)=X,(0,1)=Z,(1,1)=Y}, packed as two integer bitmasks over n
qubits; each term carries a complex coefficient. Deterministic. numpy + stdlib only.

API: spread_log2(n, circuit, observable=None, max_terms=200000) -> (float_log2, aborted_bool)
"""

from __future__ import annotations

import math

_INV_SQRT2 = 1.0 / math.sqrt(2.0)
_DROP = 1e-12          # coefficients below this are exactly-zero float noise -> pruned (keeps spread honest)

# ---- exact single-qubit Clifford conjugation tables  P -> g^dag P g  (no branching) ------------------------
# each maps the qubit's (x,z) bit pair -> single (nx, nz, factor)
_CLIFF_1Q = {
    "h":   {(0, 0): (0, 0, 1.0), (1, 0): (0, 1, 1.0), (0, 1): (1, 0, 1.0), (1, 1): (1, 1, -1.0)},
    "x":   {(0, 0): (0, 0, 1.0), (1, 0): (1, 0, 1.0), (0, 1): (0, 1, -1.0), (1, 1): (1, 1, -1.0)},
    "y":   {(0, 0): (0, 0, 1.0), (1, 0): (1, 0, -1.0), (0, 1): (0, 1, -1.0), (1, 1): (1, 1, 1.0)},
    "z":   {(0, 0): (0, 0, 1.0), (1, 0): (1, 0, -1.0), (0, 1): (0, 1, 1.0), (1, 1): (1, 1, -1.0)},
    "s":   {(0, 0): (0, 0, 1.0), (1, 0): (1, 1, -1.0), (1, 1): (1, 0, 1.0), (0, 1): (0, 1, 1.0)},
    "sdg": {(0, 0): (0, 0, 1.0), (1, 0): (1, 1, 1.0), (1, 1): (1, 0, -1.0), (0, 1): (0, 1, 1.0)},
}
_CLIFF_1Q_GATES = frozenset(_CLIFF_1Q)
_ZROT_GATES = frozenset(("t", "tdg", "rz", "p", "u1", "phase"))
# gates whose native tuple form this module understands (post-safe_parse gateset + a few synonyms/directs)
_KNOWN = _CLIFF_1Q_GATES | _ZROT_GATES | frozenset(("cx", "cnot", "cz"))


def _rz_angle(gate: tuple) -> float:
    """Return the Z-rotation angle for a gate tuple, or None if the angle is unknown (conservative T)."""
    op = gate[0]
    if op == "t":
        return math.pi / 4
    if op == "tdg":
        return -math.pi / 4
    # rz / p / u1 / phase carry an angle as the last element; may be None (atlas 'angulo desconocido')
    ang = gate[-1] if len(gate) >= 3 else None
    if ang is None:
        return None
    try:
        return float(ang)
    except (TypeError, ValueError):
        return None


def _apply_cliff_1q(terms: dict, op: str, q: int) -> dict:
    """P -> g^dag P g for a single-qubit Clifford. One-to-one, so #terms is unchanged."""
    table = _CLIFF_1Q[op]
    bit = 1 << q
    out: dict = {}
    for (x, z), c in terms.items():
        nx, nz, f = table[((x >> q) & 1, (z >> q) & 1)]
        xx = (x | bit) if nx else (x & ~bit)
        zz = (z | bit) if nz else (z & ~bit)
        key = (xx, zz)
        v = out.get(key, 0j) + c * f
        if abs(v) < _DROP:
            out.pop(key, None)
        else:
            out[key] = v
    return out


def _apply_cx(terms: dict, ctrl: int, tgt: int) -> dict:
    """P -> CX^dag P CX. Aaronson-Gottesman symplectic update; sign (-1)^{x_c z_t (x_t ^ z_c ^ 1)}."""
    cb, tb = 1 << ctrl, 1 << tgt
    out: dict = {}
    for (x, z), c in terms.items():
        xc, xt = (x >> ctrl) & 1, (x >> tgt) & 1
        zc, zt = (z >> ctrl) & 1, (z >> tgt) & 1
        sign = -1.0 if (xc & zt & (xt ^ zc ^ 1)) else 1.0
        xx = (x ^ tb) if xc else x       # x_t ^= x_c
        zz = (z ^ cb) if zt else z       # z_c ^= z_t
        key = (xx, zz)
        v = out.get(key, 0j) + c * sign
        if abs(v) < _DROP:
            out.pop(key, None)
        else:
            out[key] = v
    return out


def _apply_cz(terms: dict, a: int, b: int) -> dict:
    """P -> CZ^dag P CZ.  CZ = H_b CX_{a,b} H_b, so conjugation composes the three (each one-to-one)."""
    terms = _apply_cliff_1q(terms, "h", b)
    terms = _apply_cx(terms, a, b)
    terms = _apply_cliff_1q(terms, "h", b)
    return terms


def _apply_zrot(terms: dict, theta: float, q: int) -> dict:
    """P -> rz(theta)^dag P rz(theta).  I,Z -> unchanged;  X,Y BRANCH:
         X -> cos(th) X - sin(th) Y ,   Y -> sin(th) X + cos(th) Y.
    Identical Pauli keys are merged (coeffs add) -- crucial, else the sum overcounts."""
    c_th, s_th = math.cos(theta), math.sin(theta)
    bit = 1 << q
    out: dict = {}

    def _add(key, val):
        v = out.get(key, 0j) + val
        if abs(v) < _DROP:
            out.pop(key, None)
        else:
            out[key] = v

    for (x, z), c in terms.items():
        xq, zq = (x >> q) & 1, (z >> q) & 1
        if xq == 0:                                   # I or Z on q -> commutes, unchanged
            _add((x, z), c)
            continue
        # x-bit set: X (zq=0) or Y (zq=1).  toggling the z-bit flips X<->Y on this qubit.
        flipped = (x, z ^ bit)
        same = (x, z)
        if zq == 0:                                   # X -> cos X - sin Y
            _add(same, c * c_th)
            _add(flipped, c * (-s_th))
        else:                                         # Y -> cos Y + sin X
            _add(same, c * c_th)
            _add(flipped, c * s_th)
    return out


def _observable_terms(n: int, observable) -> dict:
    """Build the starting Pauli sum for the observable.  Default: single Z on qubit n//2.
    `observable` may be a list of qubit indices (Z on each) or None."""
    if observable is None:
        observable = [n // 2]
    z = 0
    for q in observable:
        z |= (1 << int(q))
    return {(0, z): 1.0 + 0j}


def _propagate(n: int, circuit, observable=None, max_terms: int = 200000):
    """Backward Heisenberg propagation of the observable through the circuit.

    Returns (peak_spread, final_terms, aborted, unknown_gate).
      peak_spread   : max number of live Pauli terms seen (>= 1)
      final_terms   : dict {(x,z): coeff} after the full propagation (empty if aborted/unknown)
      aborted       : True iff the term count exceeded max_terms
      unknown_gate  : the first unrecognised gate op encountered (or None)
    """
    terms = _observable_terms(n, observable)
    peak = len(terms)
    for gate in reversed(circuit):
        op = gate[0]
        if op in ("barrier", "measure", "reset", "id", "delay", "nop"):
            continue
        if op in _CLIFF_1Q_GATES:
            terms = _apply_cliff_1q(terms, op, gate[1])
        elif op in ("cx", "cnot"):
            terms = _apply_cx(terms, gate[1], gate[2])
        elif op == "cz":
            terms = _apply_cz(terms, gate[1], gate[2])
        elif op in _ZROT_GATES:
            theta = _rz_angle(gate)
            if theta is None:
                theta = math.pi / 4           # unknown Z-rotation angle -> treat as one unit of magic (T)
            terms = _apply_zrot(terms, theta, gate[1])
        else:
            return peak, {}, False, op        # unknown gate -> caller applies conservative max
        peak = max(peak, len(terms))
        if peak > max_terms:
            return peak, {}, True, None       # explosion detected early -- O(budget) work, not 2^t
    return peak, terms, False, None


def spread_log2(n: int, circuit, observable=None, max_terms: int = 200000):
    """Operator-spread tractability axis (log2 of peak Pauli-term count under backward Heisenberg propagation).

    Parameters
    ----------
    n : int
        number of qubits.
    circuit : list[tuple]
        Atlas native gate tuples: ('h',q), ('x',q), ('y',q), ('z',q), ('s',q), ('sdg',q), ('t',q),
        ('tdg',q), ('cx',c,t), ('cz',a,b), ('rz',q,theta) (and p/u1/phase synonyms).
    observable : list[int] | None
        qubit indices carrying a Z (default: single Z on qubit n//2). Local observable => cheap axis.
    max_terms : int
        term budget; if the spread exceeds it we abort early and return the saturated axis.

    Returns
    -------
    (float, bool)
        (spread_log2, aborted).  spread_log2 = log2(peak_spread).  On an UNKNOWN gate we return
        (float(n), True) -- the conservative maximum -- to never understate hardness.
    """
    peak, _final, aborted, unknown = _propagate(n, circuit, observable, max_terms)
    if unknown is not None:
        return float(n), True                 # conservative: "spreads fully, no cheap route"
    return math.log2(peak), aborted


if __name__ == "__main__":
    # tiny self-demo
    demo = [("h", 0), ("cx", 0, 1), ("t", 1), ("cx", 0, 1), ("h", 0)]
    print("spread_log2(2, bell+T) =", spread_log2(2, demo, observable=[0]))
    scr = []
    for _ in range(20):
        for q in range(6):
            scr += [("h", q), ("t", q)]
        for q in range(0, 5, 2):
            scr.append(("cx", q, q + 1))
        for q in range(1, 5, 2):
            scr.append(("cx", q, q + 1))
    print("spread_log2(6, scrambler) =", spread_log2(6, scr, max_terms=5000))

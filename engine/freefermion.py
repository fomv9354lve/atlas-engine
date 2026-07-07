"""freefermion.py -- matchgate / free-fermion THEOREM route for Atlas (deploy port).

FOURTH theorem-basis route (matchgate analog of the shipped Clifford early-exit).
Ported/adapted from HANDOFF_5ideas/freefermion.py (fold validated 30/30 accuracy,
0 false-positives, 2026-06; never deployed pending theorem grounding -- now supplied).

STATUS: detection ALWAYS runs (cheap, syntactic, additive flag+warning only).
        The route/skip behaviour is gated by env flag ATLAS_MATCHGATE (DEFAULT OFF --
        ships dark, same discipline as the original fold; with the flag off, cost_atlas
        output is byte-identical to before except the additive flag/warning).

THEOREM BASIS (why "matchgate -> classical poly" is a theorem, not a heuristic):
  * Valiant 2001 (SIAM J. Comput. 31(4)): circuits of nearest-neighbour matchgates on
    a line are classically simulable in polynomial time.
  * Terhal & DiVincenzo 2002 (PRA 65, 032325): matchgate circuits = non-interacting
    (free) fermions under Jordan-Wigner; Gaussian dynamics closes on the 2n x 2n
    Majorana covariance matrix -> O(#gates * n^3) simulation (implemented below).
  * Pfaffian amplitude-sum machinery (the operator's QED identity, verified to
    machine precision by exact subset DP -- max gap < 1e-16; source note:
    "Paper - Inverse Ginibre Overlap"/codex_only/notes/walsh_pfaffian_fermion_cousin.md):
        sum_{S subset [m], |S| even} Pf(A_S)^2 = sqrt(det(I + A^T A))
    i.e. the FULL sum of squared free-fermion amplitudes (Pfaffian minors over every
    even subset) collapses to ONE poly-time determinant. This is the fermionic
    normalization/amplitude-sum engine behind the route: overlaps and marginals of
    matchgate circuits are Pfaffians/determinants of poly-size matrices, never a
    2^n sum. Equivalently log Z_pf(A) = (1/2) log det(I + A^T A).

GUARDRAILS -- two refutations that BOUND this claim (do NOT widen the route):
  Both were tested adversarially in the same source-note corpus, and both FAILED for
  the bosonic/hafnian analog. The theorem route below is therefore FERMIONIC/PFAFFIAN
  ONLY; never extend it to hafnian-type (squared-hafnian / bosonic sampling) objects
  on the same basis:
  * Heilmann-Lieb real-rootedness REFUTED for the squared-hafnian scale polynomial:
    up to 4 non-real roots observed at m=14 (notes/global_dimer_real_rootedness_audit.md).
    The classical matching-polynomial route does NOT transfer as a black box.
  * Strong-Rayleigh / negative dependence REFUTED for the squared-hafnian vertex law:
    SR inequality violated at m=6, best_delta = -3.166 (notes/
    squared_hafnian_strong_rayleigh_audit.md). No naive stability import.
  Consequence for Atlas: is_matchgate() must stay CONSERVATIVE (whitelist, abstain on
  anything not provably a string-free Majorana quadratic). A gate with a quartic term
  (ZZ/CPHASE) leaves the Pfaffian world -- exactly where the refuted hafnian analogies
  live -- so it MUST return False.

EXACT GATESET ACCEPTED (everything else -> False, i.e. NOT matchgate):
  Single-qubit, diagonal Z-rotations (Jordan-Wigner image is the LOCAL quadratic
  (i/2) c_{2j} c_{2j+1}, string-free):
      rz(q,theta), p/u1/phase(q,theta), z(q), s(q), sdg(q), t(q), tdg(q), id/i(q).
      (t IS accepted: it is rz(pi/4), free-fermion-simulable although NON-Clifford --
       exactly where this route beats the Clifford early-exit.)
  Two-qubit, NEAREST-NEIGHBOUR ONLY (|a-b| == 1), string-free Majorana quadratics:
      iswap(a,b), sqrtiswap/siswap(a,b),
      xy/givens(a,b,theta) = exp(-i theta/2 (XX+YY)),
      rxx(a,b,theta)       = exp(-i theta/2 XX),
      ryy(a,b,theta)       = exp(-i theta/2 YY),
      hop(a,b,theta)       = exp(+i theta (XX+YY)/2)  [Atlas's native free-fermion
                             generator gate, = xy(a,b,-theta); deploy addition],
      fsim(a,b,theta,phi)  ONLY if phi == 0 (non-zero CPHASE phi is a quartic ZZ
                             term -> NOT free-fermion -> False).

EXPLICITLY REJECTED (-> False; honest exclusions of "matchgate"):
  h, x, y (Majorana STRINGS under JW), cx/cnot, cz, swap (matchgate determinant
  condition fails), ccx/ccz, rzz/cp/cphase/crz (quartic ZZ), fsim with phi != 0,
  ANY non-nearest-neighbour two-qubit gate (matchgates off the line generate
  universal QC -- the theorem is line-geometry-specific), rx/ry/sx/u2/u3, unknown
  names, malformed arity, out-of-range qubits, non-finite angles.
  NOTE: rejection is SYNTACTIC. A circuit that is unitarily free-fermion but written
  in non-matchgate gates (e.g. the {h,rz,cx} decomposition that atlas.py's QASM
  parser emits, or a hop across a 2D grid) is NOT detected -- conservative by design:
  a False here never lies; only True carries the theorem claim.

TODO (other agent owns atlas_certificate.py): label evidence_basis='theorem' for the
matchgate route there -- one-line follow-up; deliberately NOT done here.
TODO (other agent owns route_adjudicator.py): adopt the matchgate CPU certificate
natively (see _matchgate_overlay in atlas.py, which injects it from outside).

numpy only.
"""
from __future__ import annotations
import math
import os
import numpy as np

FLAG_ENV = "ATLAS_MATCHGATE"

# ---------------------------------------------------------------------------
# Gate vocabulary (see module docstring for the exact accepted set)
# ---------------------------------------------------------------------------
_ZROT_FIXED = {
    "z": math.pi,
    "s": math.pi / 2,
    "sdg": -math.pi / 2,
    "t": math.pi / 4,
    "tdg": -math.pi / 4,
    "id": 0.0,
    "i": 0.0,
}
_ZROT_ANGLE = {"rz", "p", "u1", "phase"}            # angle taken from g[2]
_TWO_Q_ANGLE = {"xy", "givens", "rxx", "ryy", "hop"}  # (name, a, b, theta)
_TWO_Q_FIXED = {                                     # (name, a, b) -> theta of exp(-i th/2 (XX+YY))
    "iswap": -math.pi / 2,
    "sqrtiswap": -math.pi / 4,
    "siswap": -math.pi / 4,
}


def _finite(x) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _gate_angle(g):
    """Z-rotation angle for a single-qubit gate tuple, or None if missing/non-finite."""
    name = g[0]
    if name in _ZROT_FIXED:
        return _ZROT_FIXED[name]
    if name in _ZROT_ANGLE:
        if len(g) < 3 or not _finite(g[2]):
            return None
        return float(g[2])
    return None


# ---------------------------------------------------------------------------
# 1) Detector (pure, conservative, never raises)
# ---------------------------------------------------------------------------
def is_matchgate_circuit(n: int, circuit) -> bool:
    """True ONLY if EVERY gate is provably a free-fermion (matchgate) operation whose
    Jordan-Wigner image is a local, string-free Majorana quadratic, AND every
    two-qubit gate is nearest-neighbour on the line. Otherwise False.

    Conservative by construction (false-safety is the worst outcome): unrecognised
    gate, wrong arity, out-of-range qubit, non-NN 2q gate, non-finite required angle,
    or non-zero fSim CPHASE -> False. Never raises on malformed input."""
    try:
        if not isinstance(n, int) or n <= 0:
            return False
        if circuit is None:
            return False
        for g in circuit:
            if not g or not isinstance(g, (tuple, list)):
                return False
            name = g[0]
            if not isinstance(name, str):
                return False
            name = name.lower()

            # --- single-qubit Z-rotations ---
            if name in _ZROT_FIXED or name in _ZROT_ANGLE:
                if len(g) < 2 or not isinstance(g[1], int):
                    return False
                if not (0 <= g[1] < n):
                    return False
                if name in _ZROT_ANGLE and (len(g) < 3 or not _finite(g[2])):
                    return False
                continue

            # --- two-qubit nearest-neighbour matchgates ---
            if name in _TWO_Q_FIXED or name in _TWO_Q_ANGLE or name == "fsim":
                if len(g) < 3 or not isinstance(g[1], int) or not isinstance(g[2], int):
                    return False
                a, b = g[1], g[2]
                if not (0 <= a < n and 0 <= b < n):
                    return False
                if abs(a - b) != 1:                       # MUST be nearest-neighbour
                    return False
                if name in _TWO_Q_ANGLE:
                    if len(g) < 4 or not _finite(g[3]):
                        return False
                elif name == "fsim":
                    # fsim(a, b, theta, phi): accept ONLY phi == 0 (else quartic ZZ ->
                    # the hafnian-side world where both guardrail refutations live)
                    if len(g) < 5 or not _finite(g[3]) or not _finite(g[4]):
                        return False
                    if abs(float(g[4])) > 1e-12:
                        return False
                continue

            # --- anything else: NOT matchgate ---
            return False
        return True
    except Exception:
        return False    # any unexpected structure -> never claim matchgate on bad input


def is_matchgate(circuit, n: int) -> bool:
    """Public detector, (circuit, n) order to match atlas.py call sites. Pure bool."""
    return is_matchgate_circuit(n, circuit)


# ---------------------------------------------------------------------------
# 2) Per-gate Majorana rotation matrices R (U c_p U^dagger = sum_a R_{ap} c_a)
# ---------------------------------------------------------------------------
def _zrot_block(theta):
    """2x2 SO(2) block for Rz(theta)=exp(-i theta/2 Z) on Majoranas (c_{2j}, c_{2j+1})."""
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, -s], [s, c]], dtype=float)


def _xy_block(theta):
    """4x4 SO(4) block for exp(-i theta/2 (XX+YY)) on adjacent modes (j, j+1),
    local Majoranas (m0,m1,m2,m3)=(c_{2j},c_{2j+1},c_{2j+2},c_{2j+3}).
    Couples (m0,m3) [YY part] and (m1,m2) [XX part]."""
    c, s = math.cos(theta), math.sin(theta)
    R = np.eye(4)
    R[0, 0], R[3, 0] = c, -s
    R[0, 3], R[3, 3] = s, c
    R[1, 1], R[2, 1] = c, s
    R[1, 2], R[2, 2] = -s, c
    return R


def _rxx_block(theta):
    """4x4 block for exp(-i theta/2 XX): couples (m1,m2) only."""
    c, s = math.cos(theta), math.sin(theta)
    R = np.eye(4)
    R[1, 1], R[2, 1] = c, s
    R[1, 2], R[2, 2] = -s, c
    return R


def _ryy_block(theta):
    """4x4 block for exp(-i theta/2 YY): couples (m0,m3) only."""
    c, s = math.cos(theta), math.sin(theta)
    R = np.eye(4)
    R[0, 0], R[3, 0] = c, -s
    R[0, 3], R[3, 3] = s, c
    return R


def _gate_majorana_R(n, g):
    """(2n x 2n) Majorana rotation for one accepted matchgate. Caller guarantees the
    gate passed the detector; raises ValueError otherwise (defensive)."""
    name = g[0].lower()
    R = np.eye(2 * n)
    if name in _ZROT_FIXED or name in _ZROT_ANGLE:
        theta = _gate_angle(g)
        j = g[1]
        R[2 * j:2 * j + 2, 2 * j:2 * j + 2] = _zrot_block(theta)
        return R
    a, b = g[1], g[2]
    j = min(a, b)
    if name in _TWO_Q_FIXED:
        blk = _xy_block(_TWO_Q_FIXED[name])
    elif name in ("xy", "givens"):
        blk = _xy_block(float(g[3]))
    elif name == "hop":
        blk = _xy_block(-float(g[3]))          # hop(th) = exp(+i th (XX+YY)/2) = xy(-th)
    elif name == "rxx":
        blk = _rxx_block(float(g[3]))
    elif name == "ryy":
        blk = _ryy_block(float(g[3]))
    elif name == "fsim":
        blk = _xy_block(float(g[3]))           # phi==0 enforced by the detector
    else:
        raise ValueError("not a recognised matchgate: %r" % (name,))
    R[2 * j:2 * j + 4, 2 * j:2 * j + 4] = blk
    return R


# ---------------------------------------------------------------------------
# 3) Free-fermion simulator (Majorana covariance evolution, O(#gates * n^3))
#    This is the constructive proof that the CPU route is real: the same object
#    whose amplitude sums the Pfaffian identity collapses to sqrt(det(I+A^T A)).
# ---------------------------------------------------------------------------
def _initial_gamma(n):
    """Gamma_{ab}=i<c_a c_b> for |0...0>: 2x2 blocks [[0,-1],[1,0]] (<Z_j>=+1)."""
    G = np.zeros((2 * n, 2 * n), dtype=float)
    for j in range(n):
        G[2 * j, 2 * j + 1] = -1.0
        G[2 * j + 1, 2 * j] = 1.0
    return G


def covariance_matrix(n: int, circuit) -> np.ndarray:
    """Evolve and return the 2n x 2n Majorana covariance matrix for U|0...0>.
    Caller must have checked is_matchgate(circuit, n)."""
    G = _initial_gamma(n)
    for g in circuit:
        R = _gate_majorana_R(n, g)
        G = R.T @ G @ R
    return G


def expval_Z(n: int, circuit) -> np.ndarray:
    """<Z_j> for j=0..n-1 (Z_j = -i c_{2j} c_{2j+1})."""
    G = covariance_matrix(n, circuit)
    return np.array([-G[2 * j, 2 * j + 1] for j in range(n)], dtype=float)


def expval_ZZ(n: int, circuit):
    """<Z_i Z_j> (i!=j) via Wick's theorem on the 2-point function; diagonal = 1."""
    G = covariance_matrix(n, circuit)
    out = np.ones((n, n), dtype=float)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a, b, c, d = 2 * i, 2 * i + 1, 2 * j, 2 * j + 1
            # Wick: <c_a c_b c_c c_d> = -(G_ab G_cd - G_ac G_bd + G_ad G_bc)
            #   with <c_p c_q> = -i Gamma_pq (p != q)  =>  <Z_i Z_j> = +(...)
            out[i, j] = (G[a, b] * G[c, d] - G[a, c] * G[b, d] + G[a, d] * G[b, c])
    return out


def freefermion_simulate(n: int, circuit) -> dict:
    """Full poly-time simulation payload (for validation / cross-checks)."""
    G = covariance_matrix(n, circuit)
    z = np.array([-G[2 * j, 2 * j + 1] for j in range(n)], dtype=float)
    return {"covariance": G, "Z": z, "ZZ": expval_ZZ(n, circuit)}


# ---------------------------------------------------------------------------
# 4) Route helpers used by atlas.py
# ---------------------------------------------------------------------------
def matchgate_enabled() -> bool:
    """True only if ATLAS_MATCHGATE is explicitly enabled. DEFAULT OFF (ships dark):
    with the flag off, only the additive detection flag + warning are emitted and
    cost_atlas behaviour is otherwise byte-identical."""
    return os.environ.get(FLAG_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def matchgate_cost_log2(n: int, n_gates: int) -> float:
    """Conservative log2 work bound for the covariance-matrix route: O(#gates * n^3)
    (a naive full 2n x 2n congruence per gate; the local-block update is cheaper).
    Never understates: real RAM is only O(n^2)."""
    return float(np.log2(max(2, int(n_gates)) * max(2, int(n)) ** 3))

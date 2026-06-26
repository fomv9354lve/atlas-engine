#!/usr/bin/env python3
"""mirror_rb — Mirror RB (Proctor et al.) con TWIRL DE PAULI CENTRAL para Atlas.

VARIANTE ELEGIDA (ver spec SPRINT2): mirror RB con Pauli-frame randomization, NO el
Loschmidt-echo crudo U·U^-1. El Loschmidt puro deja que U^-1 deshaga la rotación COHERENTE
de U -> sobreestima la fidelidad (mejor-caso coherente). El Pauli central des-correlaciona
el eco: promediado sobre Paulis, el error coherente se comporta como canal estocástico y la
return-probability mide fidelidad de PROCESO honesta.

MÉTRICA PRIMARIA: effective polarization / fidelidad efectiva corregida por el suelo:
    F = (N·P0 - 1) / (N - 1),   N = 2^n,   P0 = P(salida == t).
Es ALGEBRAICAMENTE IDÉNTICA al XEB-normalizado-por-colisión de qpu_collect_pt.py en el caso
de ideal = un único basis state (colisión Σp²=1 en vez de ~2 de Porter-Thomas):
    F_xeb = (D·E_q[p_ideal]-1)/(D·Σp²-1)  con Σp²=1, E_q[p_ideal]=P0  ->  (N·P0-1)/(N-1).

VENTAJA DE ESCALA: el ideal del espejo es UN string conocido t (computable en O(n·d) por
Pauli-frame tracking, SIN statevector). Esto rompe el techo n<=~15 del XEB (que necesita
Statevector). Mirror escala a n=50,100,127 porque el ideal es un único basis state.

DECISIONES ANTE AMBIGÜEDAD (la más simple y correcta, declaradas):
  - El CUERPO U se construye SOLO con Cliffords nativos (h, s, sdg, sx, x + cx) para que
    U·P·U^-1 sea Clifford y el string-objetivo t sea EXACTAMENTE determinista, propagando el
    Pauli-frame por el circuito (conmutación de Paulis a través de Cliffords). Así el ideal es
    O(n·d) y no requiere statevector. (Si se quisiera U no-Clifford, habría que mantener U^-1
    gate-a-gate; el ideal seguiría siendo el único string t, pero el tracking de frame requiere
    statevector — fuera de alcance de este caso simple.)
  - Twirl: forma MÍNIMA (un Pauli aleatorio central entre U y U^-1) y forma POR-CAPA (un Pauli
    tras cada capa). La por-capa es la recomendada; ambas implementadas.
  - El string objetivo t se obtiene del Pauli-frame final propagado: t = frame_Z aplicado a |0>.
  - Validación local: modelo despolarizante GLOBAL analítico con F inyectada (la misma fórmula
    de emulate_lite), sin aer, sin red, sin token.

Reutiliza random_2d_scrambling de qpu_calibration_pt para el PASO 2 (comparación XEB en circuitos
Porter-Thomas n=12).

Token-free: solo numpy + qiskit.quantum_info.Statevector / qasm2. NO qiskit-aer, NO red.
Corre la validación con:  NUMBA_DISABLE_JIT=1 python3 benchmarks/mirror_rb.py
"""
from __future__ import annotations
import json, os, random, sys

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, os.path.join(ROOT, "benchmarks"))

import numpy as np

# Reutiliza el constructor Porter-Thomas existente (para la comparación XEB del PASO 2).
from qpu_calibration_pt import random_2d_scrambling  # noqa: E402

# ---------------------------------------------------------------------------
# 1. CONSTRUCCIÓN DEL CIRCUITO ESPEJO (Clifford brickwork + Pauli twirl + inverso)
# ---------------------------------------------------------------------------

# Cliffords 1Q nativos/fáciles de invertir (nombre -> inverso). Todos Clifford.
_INV_1Q = {"h": "h", "s": "sdg", "sdg": "s", "sx": "sxdg", "sxdg": "sx", "x": "x"}
_CLIFF_1Q = ["h", "s", "sdg", "sx", "x"]

# Tablas de conjugación de Pauli por Clifford 1Q: dado un gate g y un Pauli de entrada P,
# devuelve (P', sign) tal que  g · P = (sign) · P' · g   (Pauli propagado a través de g).
# Solo necesitamos rastrear el frame de Pauli {I,X,Y,Z}; el SIGNO global no afecta el bitstring
# objetivo (la base computacional sólo ve si hay un X/Y final, no su fase) -> trackeamos P', no signo.
# Conjugación  g P g^dagger  (Heisenberg). El bitstring t lo fija la componente X/Y final.
_CONJ = {
    # H: X<->Z, Y->-Y
    "h":   {"I": "I", "X": "Z", "Y": "Y", "Z": "X"},
    # S: X->Y, Y->-X, Z->Z
    "s":   {"I": "I", "X": "Y", "Y": "X", "Z": "Z"},
    "sdg": {"I": "I", "X": "Y", "Y": "X", "Z": "Z"},
    # SX = sqrt(X): X->X, Y->Z, Z->Y  (Z<->Y)
    "sx":  {"I": "I", "X": "X", "Y": "Z", "Z": "Y"},
    "sxdg":{"I": "I", "X": "X", "Y": "Z", "Z": "Y"},
    # X: X->X, Y->-Y, Z->-Z  (frame sin signo no cambia)
    "x":   {"I": "I", "X": "X", "Y": "Y", "Z": "Z"},
}
_PAULIS = ["I", "X", "Y", "Z"]

# qelib1.inc del parser qasm2 de qiskit NO define sx/sxdg -> los definimos en el prelude
# (en términos de u, módulo fase global que no afecta la medición en base computacional).
_QASM_PRELUDE = [
    "OPENQASM 2.0;",
    'include "qelib1.inc";',
    "gate sx a { u3(pi/2,-pi/2,pi/2) a; }",
    "gate sxdg a { u3(pi/2,pi/2,-pi/2) a; }",
]


def _cz_conj(pa, pb):
    """Conjugación de un par de Paulis (pa en q_u, pb en q_v) por CZ. Devuelve (pa', pb').

    CZ: X1->X1 Z2, Z1->Z1, X2->Z1 X2, Z2->Z2 (módulo signos). En el álgebra de Pauli sin signo:
      el bit X de un qubit añade una Z en el otro. Implementamos sobre componentes (x,z).
    """
    def to_xz(p):
        return {"I": (0, 0), "X": (1, 0), "Y": (1, 1), "Z": (0, 1)}[p]
    def to_p(x, z):
        return {(0, 0): "I", (1, 0): "X", (1, 1): "Y", (0, 1): "Z"}[(x & 1, z & 1)]
    xa, za = to_xz(pa); xb, zb = to_xz(pb)
    # CZ conjugación: z_a ^= x_b ; z_b ^= x_a  (los X se propagan como Z al vecino)
    za ^= xb; zb ^= xa
    return to_p(xa, za), to_p(xb, zb)


def _grid_edges(n):
    """Aristas brickwork 2D (grid lo más cuadrado posible) consistente con random_2d_scrambling."""
    C = int(np.ceil(np.sqrt(n)))
    R = int(np.ceil(n / C))
    idx = lambda r, c: r * C + c
    edges = []
    for r in range(R):
        for c in range(C - 1):
            a, b = idx(r, c), idx(r, c + 1)
            if a < n and b < n:
                edges.append((a, b))
    for r in range(R - 1):
        for c in range(C):
            a, b = idx(r, c), idx(r + 1, c)
            if a < n and b < n:
                edges.append((a, b))
    return edges


def build_mirror_circuit(n, depth, seed, per_layer_twirl=True, no_twirl=False):
    """Construye el circuito espejo Clifford y calcula el string objetivo t por Pauli-frame.

    Estructura:  U (depth capas de [1Q Clifford random + capa CZ]) · [Pauli twirl] · U^-1.
    - per_layer_twirl=True: un Pauli aleatorio tras CADA capa de U (forma completa Proctor).
    - per_layer_twirl=False: un único Pauli central entre U y U^-1 (forma mínima).
    - no_twirl=True: Loschmidt puro U·U^-1 (caso límite de sanidad; t = 0...0).

    Devuelve dict con:
      qasm   : QASM2 del circuito espejo CON measure_all (para metal / aer).
      target : string objetivo t (str de longitud n, '0'/'1', orden big-endian q[0]..q[n-1]).
      gates_2q_layers : nº de capas CZ del circuito ESPEJO completo (= 2·depth).
      n, depth, seed, twirl
    """
    rng = random.Random(seed)
    edges = _grid_edges(n)

    # frame de Pauli acumulado (Heisenberg, propagado de DERECHA a IZQUIERDA conforme construimos).
    # Estrategia simple y correcta: construimos la lista completa de gates de U (en orden),
    # luego insertamos Paulis, luego U^-1, y propagamos el frame por TODO el circuito al final.
    body = []          # gates de U como tuplas (estilo Atlas): ("h", q) / ("cx", u, v)
    twirl_layers = []  # por capa: lista de (q, pauli)

    for d in range(depth):
        # capa 1Q random Clifford
        for q in range(n):
            body.append((rng.choice(_CLIFF_1Q), q))
        # capa CZ sobre matching del grid (greedy, no solapado)
        rng.shuffle(edges)
        used = set()
        for (u, v) in edges:
            if u not in used and v not in used:
                body.append(("cz", u, v))
                used |= {u, v}
        # twirl por capa
        if per_layer_twirl and not no_twirl:
            twirl_layers.append([(q, rng.choice(_PAULIS)) for q in range(n)])
        else:
            twirl_layers.append(None)

    # twirl central (si no es por-capa y no es no_twirl)
    central = None
    if not per_layer_twirl and not no_twirl:
        central = [(q, rng.choice(_PAULIS)) for q in range(n)]

    # Inverso de cada gate (cz autoinversa; 1Q via _INV_1Q)
    def inv_gate(g):
        if g[0] == "cz":
            return ("cz", g[1], g[2])
        return (_INV_1Q[g[0]], g[1])

    # --- ensamblar el circuito completo como lista de "eventos" ---
    # Construimos U capa-por-capa para poder intercalar el twirl por-capa, luego U^-1 en reverso.
    # Reconstruimos las capas: cada capa = (gates_1q, gates_cz). Re-derivamos del body por estructura.
    # Más simple: re-generar con el mismo rng path no es estable; en su lugar particionamos body
    # detectando los límites de capa por la presencia de cz. Construimos directo aquí:
    rng2 = random.Random(seed)
    layers = []  # cada elemento: ("U", [1q...], [cz...])
    edges2 = _grid_edges(n)
    for d in range(depth):
        g1 = [(rng2.choice(_CLIFF_1Q), q) for q in range(n)]
        rng2.shuffle(edges2)
        used = set(); gcz = []
        for (u, v) in edges2:
            if u not in used and v not in used:
                gcz.append(("cz", u, v)); used |= {u, v}
        layers.append((g1, gcz))
        if per_layer_twirl and not no_twirl:
            rng2.choice(_PAULIS)  # mantener path del rng alineado (consumimos n por capa)
            for _ in range(n - 1):
                rng2.choice(_PAULIS)
    # re-derivar twirl_layers con rng2 daría desalineo; usamos los ya muestreados con rng arriba.

    # Lista lineal de gates del circuito ESPEJO completo, en orden de aplicación (izq->der).
    full = []
    # forward U con twirl por capa
    for d, (g1, gcz) in enumerate(layers):
        full.extend(g1)
        full.extend(gcz)
        if twirl_layers[d] is not None:
            for (q, p) in twirl_layers[d]:
                if p != "I":
                    full.append((p.lower(), q))   # x/y/z como gate
    # twirl central
    if central is not None:
        for (q, p) in central:
            if p != "I":
                full.append((p.lower(), q))
    # inverso U^-1 (capas en reverso, gates de cada capa en reverso)
    for d in range(depth - 1, -1, -1):
        g1, gcz = layers[d]
        for g in reversed(gcz):
            full.append(inv_gate(g))
        for g in reversed(g1):
            full.append(inv_gate(g))

    # --- propagación del Pauli-frame para obtener t (Heisenberg, de IZQ a DER) ---
    # Iniciamos con frame = todos los Paulis 'Z' de la medición final propagados hacia atrás? No:
    # forma directa -> propagamos el efecto de los Paulis INSERTADOS hasta el final del circuito,
    # conjugándolos por todas las puertas (Clifford) que vienen DESPUÉS de cada Pauli, y leemos
    # la componente X/Y resultante en cada qubit (que voltea el bit medido respecto a |0>).
    # Implementación robusta: mantenemos un frame por qubit y recorremos `full` de izq a der.
    # frame[q] in {I,X,Y,Z}: Pauli pendiente justo ANTES de la siguiente puerta en q.
    frame = ["I"] * n
    for g in full:
        if g[0] == "cz":
            u, v = g[1], g[2]
            frame[u], frame[v] = _cz_conj(frame[u], frame[v])
        elif g[0] in ("x", "y", "z"):
            # Pauli insertado: se MULTIPLICA en el frame (composición de Paulis, sin signo)
            q = g[1]
            frame[q] = _pauli_mul(frame[q], g[0].upper())
        else:
            # Clifford 1Q: conjuga el frame existente
            q = g[1]
            frame[q] = _CONJ[g[0]][frame[q]]

    # El bit medido en q es 1 si el frame final tiene componente X o Y (anti-conmuta con Z) -> voltea |0>.
    target = "".join("1" if frame[q] in ("X", "Y") else "0" for q in range(n))

    # --- QASM ---
    L = list(_QASM_PRELUDE) + ["qreg q[%d];" % n, "creg c[%d];" % n]
    for g in full:
        if g[0] == "cz":
            L.append("cz q[%d],q[%d];" % (g[1], g[2]))
        elif g[0] == "y":
            L.append("y q[%d];" % g[1])
        else:
            L.append("%s q[%d];" % (g[0], g[1]))
    for q in range(n):
        L.append("measure q[%d] -> c[%d];" % (q, q))
    qasm = "\n".join(L) + "\n"

    n2q_layers = 2 * depth
    return {"qasm": qasm, "target": target, "n": n, "depth": depth, "seed": seed,
            "twirl": ("none" if no_twirl else ("per_layer" if per_layer_twirl else "central")),
            "gates_2q_layers": n2q_layers}


def _pauli_mul(a, b):
    """Producto de dos Paulis ignorando signo (grupo de Pauli mod fase)."""
    if a == "I":
        return b
    if b == "I":
        return a
    if a == b:
        return "I"
    s = {a, b}
    if s == {"X", "Y"}:
        return "Z"
    if s == {"X", "Z"}:
        return "Y"
    if s == {"Y", "Z"}:
        return "X"
    return "I"


# ---------------------------------------------------------------------------
# 2. ESTIMADOR DE FIDELIDAD EFECTIVA (corrección depolarizante)
# ---------------------------------------------------------------------------

def fidelity_from_return_prob(p0, n):
    """Effective polarization / fidelidad efectiva: F = (N·P0 - 1)/(N - 1), N=2^n.

    Inversión exacta del modelo despolarizante global rho = F·|t><t| + (1-F)·I/N.
    F=1 -> P0=1 ; F=0 -> P0=1/N. Idéntica al XEB-por-colisión con Σp²=1.
    """
    N = 2 ** n
    return (N * p0 - 1.0) / (N - 1.0)


def return_prob_from_counts(counts, target):
    """P0 = P(salida == t) desde un dict de counts {bitstring: shots}."""
    tot = sum(counts.values())
    if tot == 0:
        return 0.0
    hit = 0
    for bits, c in counts.items():
        if bits.replace(" ", "") == target:
            hit += c
    return hit / tot


# ---------------------------------------------------------------------------
# 3. VALIDACIÓN LOCAL (sin QPU, sin aer): modelo despolarizante global analítico
# ---------------------------------------------------------------------------

def _sample_mirror_p0(target, n, F_inject, shots, rng):
    """Muestrea P0_hat del modelo despolarizante global para el ESPEJO (ideal = |t>).

    q(x) = F·[x==t] + (1-F)/N. Sin statevector: el ideal es delta en t.
    Muestreo multinomial colapsado: cada shot cae en t con prob (F + (1-F)/N) y en cualquiera
    de los N estados con (1-F)/N (incluido t). P(x==t) = F + (1-F)/N.
    """
    N = 2 ** n
    p0_true = F_inject + (1.0 - F_inject) / N
    hits = rng.binomial(shots, p0_true)
    return hits / shots


def _xeb_from_model(p_ideal, F_inject, shots, rng):
    """XEB (qpu_collect_pt) bajo el MISMO modelo despolarizante global.

    q = F·p_ideal + (1-F)/N. Estima F_XEB = (D·E_q[p_ideal]-1)/(D·Σp²-1).
    Con shots: muestrea bitstrings de q y promedia p_ideal observado. shots=None -> límite analítico.
    """
    N = len(p_ideal)
    q = F_inject * p_ideal + (1.0 - F_inject) / N
    q = q / q.sum()
    sum_p2 = float((p_ideal ** 2).sum())
    if shots is None:
        eqp = float((q * p_ideal).sum())   # E_q[p_ideal] exacto
    else:
        idx = rng.choice(N, size=shots, p=q)
        eqp = float(p_ideal[idx].mean())
    denom = N * sum_p2 - 1.0
    return (N * eqp - 1.0) / denom if denom > 0 else 0.0


def validate_local(n=12, F_list=(0.9, 0.7, 0.5), depth=4, shots=8192, seed0=1234, n_circuits=8):
    """PASO 1 + PASO 2: mirror recupera F inyectada y coincide con XEB en el mismo modelo.

    Para cada F inyectada:
      - mirror: construye n_circuits espejos (twirl por-capa), muestrea P0 del modelo
        despolarizante global, promedia, estima F via (N·P0-1)/(N-1).
      - xeb: usa un circuito Porter-Thomas (random_2d_scrambling) n=12, statevector exacto
        para p_ideal, mismo modelo despolarizante, estima F_XEB.
    Devuelve lista de filas dict y un dict de asserts. Tolerancia ±0.05.
    """
    rng = np.random.default_rng(seed0)
    rows = []
    ok_recover = True
    ok_agree = True
    # p_ideal para XEB: un circuito PT fijo n=12 (sin measure -> statevector)
    from qiskit.qasm2 import loads as qload
    from qiskit.quantum_info import Statevector
    pt_qasm = random_2d_scrambling(n, depth, seed=777)
    p_ideal = np.abs(Statevector.from_instruction(qload(pt_qasm)).data) ** 2
    p_ideal = p_ideal / p_ideal.sum()

    for F in F_list:
        # ---- mirror: promediar sobre n_circuits espejos aleatorios ----
        p0s = []
        for k in range(n_circuits):
            mc = build_mirror_circuit(n, depth, seed=seed0 + 31 * k, per_layer_twirl=True)
            p0 = _sample_mirror_p0(mc["target"], n, F, shots, rng)
            p0s.append(p0)
        p0_bar = float(np.mean(p0s))
        F_mirror = fidelity_from_return_prob(p0_bar, n)

        # ---- mirror límite analítico (shots->inf): debe dar F EXACTO ----
        N = 2 ** n
        p0_exact = F + (1.0 - F) / N
        F_mirror_exact = fidelity_from_return_prob(p0_exact, n)

        # ---- xeb mismo modelo ----
        F_xeb = _xeb_from_model(p_ideal, F, shots, rng)
        F_xeb_exact = _xeb_from_model(p_ideal, F, None, rng)

        rec = abs(F_mirror - F) <= 0.05
        agr = abs(F_mirror - F_xeb) <= 0.05
        ok_recover = ok_recover and rec
        ok_agree = ok_agree and agr
        rows.append({"F_inject": F, "F_mirror": round(F_mirror, 4),
                     "F_mirror_exact": round(F_mirror_exact, 6),
                     "F_xeb": round(F_xeb, 4), "F_xeb_exact": round(F_xeb_exact, 6),
                     "P0_bar": round(p0_bar, 5), "recover_ok": rec, "agree_ok": agr})
    return rows, {"all_recover_within_0.05": ok_recover, "all_agree_within_0.05": ok_agree}


def validate_twirl_sanity(n=8, depth=6, seed=4242, coherent_angle=0.25, shots=20000, n_paulis=64):
    """SANIDAD DEL TWIRL: ruido COHERENTE residual.

    Loschmidt puro (no twirl): U^-1 deshace la rotación coherente -> P0 inflada -> F sobreestimada.
    Con twirl por Paulis promediados: el error coherente se des-correlaciona -> F vuelve al valor
    despolarizante efectivo (mucho menor que el inflado).

    Modelo simplificado token-free: tras CADA capa CZ inyectamos una sobre-rotación coherente Rz(eps)
    en cada qubit (canal unitario residual). En el eco SIN twirl la inversa lo cancela casi exacto.
    Con twirl, el Pauli central anti-conmuta parcialmente y rompe la cancelación. Lo modelamos en el
    nivel de la fidelidad efectiva del eco:
      - sin twirl: la fidelidad coherente del eco ~ |<0|U^-1 R^-1 R U|0>|^2 -> ~1 (cancela) -> F~1.
      - con twirl (promedio sobre Paulis): F_eff = fidelidad despolarizante = ~ (cos eps)^(2·#capas).
    Demostramos el GAP con statevector exacto a n pequeño.
    """
    from qiskit.qasm2 import loads as qload
    from qiskit.quantum_info import Statevector

    # capas FIJAS de U (mismas para Loschmidt y twirled, para comparación limpia)
    rng = random.Random(seed)
    edges = _grid_edges(n)
    layers = []
    for d in range(depth):
        g1 = [(rng.choice(_CLIFF_1Q), q) for q in range(n)]
        rng.shuffle(edges); used = set(); gcz = []
        for (u, v) in edges:
            if u not in used and v not in used:
                gcz.append((u, v)); used |= {u, v}
        layers.append((g1, gcz))

    def echo_qasm(twirl_pauli):
        """U · (R) · [Pauli] · (R) · U^-1 con sobre-rotación coherente Rz(eps) tras cada CZ-layer.
        twirl_pauli: None (Loschmidt) o lista de Paulis centrales por qubit."""
        L = list(_QASM_PRELUDE) + ["qreg q[%d];" % n]
        eps = coherent_angle
        # forward U + coherente
        for (g1, gcz) in layers:
            for (gn, q) in g1:
                L.append("%s q[%d];" % (gn, q))
            for (u, v) in gcz:
                L.append("cz q[%d],q[%d];" % (u, v))
            for q in range(n):
                L.append("rz(%f) q[%d];" % (eps, q))   # error coherente residual
        # twirl central
        if twirl_pauli is not None:
            for q, p in enumerate(twirl_pauli):
                if p != "I":
                    L.append("%s q[%d];" % (p.lower(), q))
        # inverso (incluye deshacer el coherente -> SIN twirl cancela)
        for (g1, gcz) in reversed(layers):
            for q in range(n):
                L.append("rz(%f) q[%d];" % (-eps, q))
            for (u, v) in reversed(gcz):
                L.append("cz q[%d],q[%d];" % (u, v))
            for (gn, q) in reversed(g1):
                inv = _INV_1Q[gn]
                L.append("%s q[%d];" % (inv, q))
        return "\n".join(L) + "\n", twirl_pauli

    def frame_target_for_central(twirl_pauli):
        """String objetivo t para un Pauli central dado, por propagación EXACTA del frame
        (Heisenberg, idéntica a build_mirror_circuit) sobre el circuito SIN el ruido coherente.

        El ruido rz(eps) es diagonal (solo fase Z) y no cambia el basis state objetivo en el eco
        ideal; t lo fijan los Cliffords + el Pauli central. Construimos el frame recorriendo
        U · P · U^-1 (sin rz) en orden de aplicación."""
        # gates lineales del eco IDEAL (sin rz) con este Pauli central
        full = []
        for (g1, gcz) in layers:
            full.extend(g1)
            full.extend([("cz", u, v) for (u, v) in gcz])
        if twirl_pauli is not None:
            for q, p in enumerate(twirl_pauli):
                if p != "I":
                    full.append((p.lower(), q))
        for (g1, gcz) in reversed(layers):
            for (u, v) in reversed(gcz):
                full.append(("cz", u, v))
            for (gn, q) in reversed(g1):
                full.append((_INV_1Q[gn], q))
        frame = ["I"] * n
        for g in full:
            if g[0] == "cz":
                frame[g[1]], frame[g[2]] = _cz_conj(frame[g[1]], frame[g[2]])
            elif g[0] in ("x", "y", "z"):
                frame[g[1]] = _pauli_mul(frame[g[1]], g[0].upper())
            else:
                frame[g[1]] = _CONJ[g[0]][frame[g[1]]]
        return "".join("1" if frame[q] in ("X", "Y") else "0" for q in range(n)), frame

    def p_at_target(psi, target):
        # índice del basis state en qiskit: el qubit q pesa (1<<q). target[q] es el bit del qubit q.
        ii = 0
        for q in range(n):
            if target[q] == "1":
                ii |= (1 << q)
        return float(psi[ii])

    # SIN twirl (Loschmidt): el eco coherente se CANCELA (rz(eps)·rz(-eps)) -> P0~1 -> F sobreestimada
    qasm0, _ = echo_qasm(None)
    psi0 = np.abs(Statevector.from_instruction(qload(qasm0)).data) ** 2
    t0, _ = frame_target_for_central(None)         # = "0...0"
    p0_loschmidt = p_at_target(psi0, t0)
    F_loschmidt = fidelity_from_return_prob(p0_loschmidt, n)

    # CON twirl: el Pauli central NO conmuta con la rz residual -> P·rz(eps)·P ≠ rz(eps), la inversa
    # rz(-eps) ya NO cancela. Promediado sobre Paulis aleatorios -> P0 honesta (eco roto) -> F real.
    rngp = random.Random(seed + 1)
    p0_twirled = []
    for _ in range(n_paulis):
        tw = [rngp.choice(_PAULIS) for _ in range(n)]
        qasm, _ = echo_qasm(tw)
        psi = np.abs(Statevector.from_instruction(qload(qasm)).data) ** 2
        t, _ = frame_target_for_central(tw)        # target EXACTO para este Pauli (frame propagado)
        p0_twirled.append(p_at_target(psi, t))
    p0_tw = float(np.mean(p0_twirled))
    F_twirled = fidelity_from_return_prob(p0_tw, n)

    return {"n": n, "depth": depth, "coherent_angle": coherent_angle,
            "P0_loschmidt": round(p0_loschmidt, 5), "F_loschmidt(no_twirl)": round(F_loschmidt, 5),
            "P0_twirled": round(p0_tw, 5), "F_twirled": round(F_twirled, 5),
            "gap": round(F_loschmidt - F_twirled, 5),
            "interpretation": "Error COHERENTE residual rz(eps) tras cada capa. SIN twirl el eco "
                              "U^-1 lo cancela exacto (rz(eps)·rz(-eps)=I) -> F_loschmidt~1 = "
                              "SOBREESTIMACIÓN del mejor-caso coherente. CON twirl el Pauli central "
                              "anti-conmuta con rz (X/Y·Rz·X/Y = Rz(-eps)) y rompe la cancelación; "
                              "promediado sobre Paulis -> F_twirled honesta < F_loschmidt. El gap "
                              "demuestra por qué Proctor exige Pauli-frame randomization, no Loschmidt crudo."}


def validate_target_correctness(ns=(4, 6, 8, 10), depths=(4, 8), seed0=777):
    """NO-CIRCULAR: prueba que el string objetivo computado por Pauli-frame (O(n·d), SIN statevector)
    es EXACTAMENTE el output del circuito real. Construye el circuito espejo, lo corre por statevector
    EXACTO sin ruido, y verifica que toda la masa cae en `target` (P0=1). Cierra el caveat de
    circularidad: el método mirror es válido a n grande PORQUE el target es demostrablemente correcto
    a n chico (donde sí podemos simular), para los 3 modos de twirl."""
    from qiskit.qasm2 import loads as qload
    from qiskit.quantum_info import Statevector
    rows = []
    ok_all = True
    for n in ns:
        for depth in depths:
            for mode, kw in (("per_layer", {"per_layer_twirl": True}),
                             ("central", {"per_layer_twirl": False}),
                             ("no_twirl", {"no_twirl": True})):
                mc = build_mirror_circuit(n, depth, seed0 + n + depth, **kw)
                qc = qload(mc["qasm"]); qc.remove_final_measurements(inplace=True)  # statevector no admite measure
                probs = Statevector.from_instruction(qc).probabilities()
                i = int(probs.argmax())
                actual = "".join(str((i >> q) & 1) for q in range(n))  # big-endian q0..q(n-1)
                p0 = float(probs[i])
                hit = (actual == mc["target"]) and p0 > 0.999
                ok_all = ok_all and hit
                rows.append((n, depth, mode, p0, hit))
    return {"rows": rows, "all_targets_correct": ok_all}


# ---------------------------------------------------------------------------
# __main__ : corre la validación e imprime la tabla
# ---------------------------------------------------------------------------

def main():
    n = 12
    F_list = (0.9, 0.7, 0.5)
    print("=" * 78)
    print("MIRROR RB (Proctor, twirl de Pauli) — VALIDACIÓN LOCAL token-free (n=%d)" % n)
    print("Modelo: despolarizante global  rho = F·|t><t| + (1-F)·I/N   (idéntico a emulate_lite)")
    print("Estimador primario: F = (N·P0 - 1)/(N - 1)  == XEB-por-colisión con Σp²=1")
    print("=" * 78)

    rows, asserts = validate_local(n=n, F_list=F_list, depth=4, shots=8192, n_circuits=8)

    print("\nPASO 1+2 — tabla F_inject vs F_mirror vs F_xeb (mismo modelo, n=%d):\n" % n)
    hdr = "  %-9s | %-9s | %-13s | %-9s | %-13s | %-8s | %-6s | %-6s"
    print(hdr % ("F_inject", "F_mirror", "F_mirror(S→∞)", "F_xeb", "F_xeb(S→∞)", "P0_bar", "rec", "agree"))
    print("  " + "-" * 92)
    for r in rows:
        print("  %-9.3f | %-9.4f | %-13.6f | %-9.4f | %-13.6f | %-8.5f | %-6s | %-6s" % (
            r["F_inject"], r["F_mirror"], r["F_mirror_exact"], r["F_xeb"], r["F_xeb_exact"],
            r["P0_bar"], "OK" if r["recover_ok"] else "FAIL", "OK" if r["agree_ok"] else "FAIL"))

    print("\nASSERTS:")
    print("  mirror recupera F_inject dentro de ±0.05 (todas):  %s" % asserts["all_recover_within_0.05"])
    print("  mirror ≈ XEB dentro de ±0.05 (todas):              %s" % asserts["all_agree_within_0.05"])

    # PRUEBA NO-CIRCULAR: el target del Pauli-frame == output real (statevector exacto, sin ruido)
    print("\nNO-CIRCULAR — target del Pauli-frame == output del circuito REAL (statevector exacto, P0=1):")
    tc = validate_target_correctness(ns=(4, 6, 8, 10), depths=(4, 8))
    for (nn, dd, mode, p0, hit) in tc["rows"]:
        if not hit:
            print("  ✗ n=%d depth=%d twirl=%s  P0=%.4f  TARGET INCORRECTO" % (nn, dd, mode, p0))
    print("  todos los targets (n=4,6,8,10 × depth 4,8 × 3 modos twirl) correctos con P0=1: %s"
          % tc["all_targets_correct"])
    print("  -> cierra la circularidad: el método NO asume el ideal, lo PRUEBA donde se puede simular.")

    # demo de construcción + escala del target O(n·d) sin statevector
    print("\nDEMO ESCALA — string objetivo computado SIN statevector (Pauli-frame O(n·d)):")
    for nn in (12, 50, 100, 127):
        mc = build_mirror_circuit(nn, depth=8, seed=2026, per_layer_twirl=True)
        print("  n=%-3d depth=8  capas_2q(espejo)=%-3d  target[:24]=%s...  twirl=%s"
              % (nn, mc["gates_2q_layers"], mc["target"][:24], mc["twirl"]))

    print("\nSANIDAD TWIRL (error coherente residual rz(eps), statevector exacto n=8):")
    sanity = validate_twirl_sanity(n=8, depth=6, coherent_angle=0.25, n_paulis=64)
    print("  F_loschmidt(no_twirl)=%.5f  >  F_twirled=%.5f   (gap=%.5f)" %
          (sanity["F_loschmidt(no_twirl)"], sanity["F_twirled"], sanity["gap"]))
    twirl_ok = sanity["F_loschmidt(no_twirl)"] > sanity["F_twirled"] + 0.1
    print("  twirl rompe la cancelación coherente (Loschmidt sobreestima): %s" % twirl_ok)
    print("  nota: %s" % sanity["interpretation"])

    overall = (asserts["all_recover_within_0.05"] and asserts["all_agree_within_0.05"]
               and tc["all_targets_correct"] and twirl_ok)
    print("\n%s VALIDACIÓN %s" % ("[OK]" if overall else "[FAIL]", "PASA" if overall else "FALLA"))
    return overall


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)

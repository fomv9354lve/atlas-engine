"""ground_truth.py -- MPS y treewidth REALES (cotas estructurales -> medidas exactas).

Reemplaza los proxies del arsenal por las herramientas de referencia del campo:
  - MPS bond: quimb CircuitMPS (simulacion MPS exacta, incluye los rz -> sin el bug del cx-rz-cx que se
              cancelaba en el estimador estructural del arsenal). Con cap de bond + flag de truncacion.
  - treewidth: cotengra (via quimb contraction_width) -- el optimizador de contraccion de referencia.

Asi MPS y treewidth dejan de ser cotas del circuito y pasan a ser medidas reales del estado/contraccion.
"""
from __future__ import annotations
import numpy as np
try:
    import numba
    import numba.core.decorators as _numba_dec
    import numba.np.ufunc.decorators as _numba_udec

    def _no_numba_cache(orig):
        def wrapper(*args, **kwargs):
            kwargs["cache"] = False
            return orig(*args, **kwargs)
        return wrapper

    numba.njit = _no_numba_cache(numba.njit)
    numba.jit = _no_numba_cache(numba.jit)
    numba.vectorize = _no_numba_cache(numba.vectorize)
    _numba_dec.njit = numba.njit
    _numba_dec.jit = numba.jit
    _numba_udec.vectorize = numba.vectorize
except Exception:
    pass
import quimb.tensor as qtn
import stim

_1Q = {"h": "H", "s": "S", "t": "T", "x": "X", "y": "Y", "z": "Z", "sdg": "SDG", "tdg": "TDG"}
_STIM = {"h": "H", "s": "S", "x": "X", "y": "Y", "z": "Z", "cx": "CX", "cz": "CZ"}


def stim_is_clifford(circuit) -> bool:
    """¿Clifford? ⟺ todas las compuertas en la base Clifford (en _STIM, sin T). Unified Core (2026-06-24):
    el chequeo es de GATE-SET; construir un stim.Circuit solo para verificarlo era redundante (~2.3s en
    n=18 Clifford medido). El scan de nombres da el MISMO booleano en microsegundos (~30000x). La
    equivalencia-Clifford con T's que cancelan se maneja aparte (reducción del parser + is_clifford_exact
    n<=9 en cross_validate). Fuente: benchmarks/unified_core.md.
    NOTA: idéntico al método anterior salvo el caso (imposible post-safe_parse) de una compuerta de la base
    con aridad malformada — el parser garantiza compuertas bien formadas."""
    for g in circuit:
        if not g or g[0] == "t" or g[0] not in _STIM:
            return False
    return True


SV_QUBIT_CAP = 22   # statevector exacto: 2^22 amps ~ 32 MB de probabilidades (rápido para un request web)


def compute_result(n, circuit, t_count, qasm=None, route=None, mps_truncated=False, shots=4096):
    """El '+' de la propuesta de valor: ENTREGA el resultado SOLO donde el triage certificó barato.

    Gateado por el veredicto (nunca corre el caso duro a ciegas):
      - Clifford (#T=0): Stim, EXACTO a cualquier n (muestreo de estabilizadores).
      - n<=SV_QUBIT_CAP: statevector exacto.
      - resto (n grande no-Clifford): NO computa; devuelve el veredicto como respuesta honesta.
    Returns dict con computed/method/top (bitstrings big-endian q0..q(n-1) -> prob) o computed=False+reason.
    """
    # Clifford -> Stim (exacto, cualquier n)
    if t_count == 0:
        try:
            c = stim.Circuit()
            for g in circuit:
                if g[0] in _STIM:
                    c.append(_STIM[g[0]], list(g[1:]))
            for q in range(n):
                c.append("M", [q])
            sample = c.compile_sampler().sample(shots=shots)
            counts = {}
            for row in sample:
                bs = "".join("1" if row[q] else "0" for q in range(n))
                counts[bs] = counts.get(bs, 0) + 1
            top = {k: round(v / shots, 4) for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:12]}
            return {"computed": True, "method": "Stim (Clifford, EXACTO a cualquier n)", "exact": True,
                    "sampled_shots": shots, "n": n, "route": route, "top": top,
                    "note": "estabilizador-simulable: #T=0 -> coste polinomial certificado; muestreo exacto."}
        except Exception as e:
            return {"computed": False, "reason": "Stim falló: " + str(e)[:120], "route": route}
    # statevector exacto si 2^n cabe
    if n <= SV_QUBIT_CAP and qasm:
        try:
            import numpy as np
            from qiskit.qasm2 import loads as qload
            from qiskit.quantum_info import Statevector
            p = np.abs(Statevector.from_instruction(qload(qasm)).data) ** 2
            idx = np.argsort(p)[::-1][:12]
            top = {format(int(i), "0%db" % n): round(float(p[i]), 4) for i in idx if p[i] > 1e-6}
            return {"computed": True, "method": "statevector exacto (2^%d cabe)" % n, "exact": True,
                    "n": n, "route": route, "top": top,
                    "note": "n<=%d -> el estado completo cabe en memoria; distribución ideal EXACTA." % SV_QUBIT_CAP}
        except Exception as e:
            return {"computed": False, "reason": "statevector falló: " + str(e)[:120], "route": route}
    # caso no certificado barato -> el veredicto ES la respuesta (no inventamos un número)
    why = ("n=%d > %d y no-Clifford" % (n, SV_QUBIT_CAP))
    if mps_truncated:
        why += " (y el MPS se truncó -> no es exacto)"
    return {"computed": False, "route": route,
            "reason": "No certificado barato para cómputo exacto en el app: %s. Ese es el veredicto: "
                      "el caso es duro, defer a %s. (Atlas no ejecuta a ciegas el caso que marcó duro.)"
                      % (why, route or "la ruta indicada")}


def cross_validate(n, circuit, t_count, mps_log2, tw_log2, mps_truncated, spread_log2=None, tw_exact=False):
    """LA capa que el audit pedia: cross-validacion entre los metodos, no solo correr cada uno en solitario.
    Devuelve flags por-metodo + tests de consistencia + warnings. Esto es el moat (nadie mas lo hace)."""
    methods = {"stim": True, "quimb": True, "cotengra": True, "pauli": True}
    val, warns = {}, []
    stim_cliff = stim_is_clifford(circuit)
    # (1) t_count del parser vs Stim: (#T==0) debe coincidir con que Stim acepte el circuito como Clifford.
    expect_cliff = (t_count == 0)
    val["tcount_vs_stim"] = "ok" if stim_cliff == expect_cliff else "DIVERGENCIA"
    if stim_cliff != expect_cliff:
        warns.append(f"divergencia parser/Stim: #T={t_count} pero Stim "
                     f"{'lo acepta como Clifford' if stim_cliff else 'lo rechaza (no-Clifford)'}")
    # (1b) EXACTO (n<=6): test de Clifford del UNITARIO -> caza el caso borde Clifford-equivalente con T's.
    try:
        from exact import is_clifford_exact
        ce = is_clifford_exact(n, circuit)
        if ce is not None:
            val["clifford_exact"] = bool(ce)
            if ce and t_count > 0:
                val["magic_exact"] = "SOBRE-CONTADA"
                warns.append(f"magia sintactica #T={t_count} pero el UNITARIO es Clifford (n<=9, EXACTO): "
                             f"el circuito es Clifford-equivalente, magia real = 0")
            elif (not ce) and t_count == 0:
                val["magic_exact"] = "SUB-CONTADA"
                warns.append("magia #T=0 pero el unitario NO es Clifford (n<=9, EXACTO): posible bug")
            else:
                val["magic_exact"] = "ok (verificado exacto)"
    except Exception:
        pass
    # (2) spread (pauli-prop) vs Stim -- CIERRA LA DEUDA #1. spread = log2(#terminos Pauli). Un Clifford
    #     evoluciona un Pauli local a UN solo Pauli (Stim lo confirma exacto) -> spread DEBE ser ~2^0.
    if spread_log2 is not None:
        if stim_cliff:
            ok = spread_log2 <= 0.5
            val["spread_vs_stim"] = "ok" if ok else "DIVERGENCIA"
            if not ok:
                warns.append(f"Clifford pero spread=2^{spread_log2}>2^0: pauli-prop deberia mantener 1 "
                             f"termino (Stim: el operador sigue siendo un solo Pauli) -> posible bug en spread")
        else:
            val["spread_vs_stim"] = "n/a (no-Clifford: el spread crece genuinamente; sin chequeo exacto barato)"
    # (3) MPS: ¿el bond se trunco al cap? Entonces el coste MPS es COTA INFERIOR (subestimado).
    val["mps_truncated"] = bool(mps_truncated)
    if mps_truncated:
        warns.append("MPS truncado al cap de bond -> el coste MPS reportado es COTA INFERIOR (subestimado)")
    # (4) consistencia MPS vs treewidth: log2(bond) <= treewidth (la contraccion acota el bond).
    val["mps_tw_consistency"] = "ok" if mps_log2 <= tw_log2 + 1e-6 else "INCONSISTENTE"
    if mps_log2 > tw_log2 + 1e-6:
        warns.append(f"inconsistencia interna: MPS log2={mps_log2} > treewidth={tw_log2} "
                     f"(el bond no puede exceder el treewidth) -> posible bug")
    # (4b) divergencia treewidth(greedy) vs MPS (audit 2026-06): si el treewidth cota-superior excede al bond
    #      EXACTO por un margen grande (brick-wall: 2^12 tw vs 2^2 bond), el veredicto se apoya SOLO en MPS y el
    #      greedy sobreestima la dureza. Señalarlo para que nadie lea el treewidth como "dureza real".
    if (not tw_exact) and (not mps_truncated) and (tw_log2 - mps_log2) > 8.0:
        val["tw_mps_divergence"] = "ALTA"
        warns.append(f"estimadores muy divergentes: treewidth=2^{tw_log2:.1f} (cota sup. greedy) >> MPS=2^{mps_log2:.1f} "
                     f"(exacto). El veredicto se apoya en MPS; el treewidth greedy sobreestima en esta topologia "
                     f"-- NO leer el treewidth como dureza real.")
    val["treewidth_exact"] = bool(tw_exact)
    note = ("treewidth = OPTIMO EXACTO (busqueda de camino de contraccion optimo)" if tw_exact
            else "treewidth = cota superior heuristica (greedy; el exacto es NP-duro para esta red)")
    return {"methods": methods, "validations": val, "warnings": warns, "cotengra_note": note,
            "stim_clifford": bool(stim_cliff)}


def _build(circ, circuit):
    for g in circuit:
        op = g[0]
        if op in _1Q:
            circ.apply_gate(_1Q[op], g[1])
        elif op in ("cx", "cnot"):
            circ.apply_gate("CX", g[1], g[2])
        elif op == "cz":
            circ.apply_gate("CZ", g[1], g[2])
        elif op == "rz":
            circ.apply_gate("RZ", g[2], g[1])
        # hop/desconocidos: se ignoran (no deberian llegar; el generador descompone hop)
    return circ


def mps_bond_log2(n, circuit, max_bond=None):
    """Bond MPS REAL via quimb (cutoff 1e-10). Devuelve (log2 del bond, ¿truncado?).

    CIERRA LA DEUDA #2: el bond exacto de un estado de n qubits nunca excede 2^(n/2). Fijamos el cap a
    min(2^(n/2), 1024); asi para n<=20 el MPS es SIEMPRE exacto (nunca trunca, nunca es cota inferior).
    El tope 1024 acota la memoria (~n*1024^2*16B < 1GB) para n>20, donde si puede truncar (lo flageamos)."""
    theo_max = 1 << (n // 2)                               # bond exacto maximo de n qubits (corte central)
    if max_bond is None:
        # n<=20: exacto (cap = maximo teorico, <=1024). n>20: cap 2^6 -> el MPS denso se computa en ~1-2s
        # (a bond 256 tardaba >3min). La truncacion es honesta: no afirma ruta MPS, y si treewidth tambien
        # excede el presupuesto el veredicto es INTRACTABLE. Solo necesitamos SABER que trunca, no el bond real.
        max_bond = min(theo_max, 1024 if n <= 20 else 64)
    circ = qtn.CircuitMPS(n, gate_opts={"max_bond": max_bond, "cutoff": 1e-10})
    _build(circ, circuit)
    b = int(circ.psi.max_bond())
    # truncado SOLO si tocamos un cap ARTIFICIAL (< maximo teorico). Tocar el maximo teorico = EXACTO.
    truncated = (b >= max_bond) and (max_bond < theo_max)
    return float(np.log2(max(1, b))), truncated


def treewidth_log2(n, circuit, optimize=None):
    """Ancho de contraccion (treewidth) via quimb/cotengra. log2 del mayor tensor intermedio.

    CIERRA LA DEUDA #1: el treewidth EXACTO es NP-duro EN GENERAL, pero el camino de contraccion OPTIMO si es
    computable para redes pequenas (programacion dinamica). Usamos 'optimal'/'dp' (EXACTO) por debajo de un
    umbral de tensores, y 'greedy' (cota superior heuristica) por encima. Devuelve (log2, exacto?)."""
    circ = qtn.Circuit(n)
    _build(circ, circuit)
    psi = circ.psi
    n_tensors = psi.num_tensors
    if optimize is not None:
        return float(psi.contraction_width(optimize=optimize)), False
    # La busqueda OPTIMA (exacta) es factorial: <0.1s a ~24 tensores, pero ~5s a 32 y ~33s mas alla.
    # Umbral medido y CONSERVADOR (<=24 tensores) -> exacto e instantaneo; greedy (heuristico) arriba.
    if n_tensors <= 24:
        return float(psi.contraction_width(optimize="optimal")), True       # EXACTO (busqueda optima)
    return float(psi.contraction_width(optimize="greedy")), False           # cota superior heuristica


def main():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from atlas import build_target, decompose
    print("ground_truth -- MPS (quimb) y treewidth (cotengra) reales\n")
    # el circuito generado 'core' que daba MPS 2^0 falso en el arsenal:
    for tag, book in [("core", "core"), ("free", "free")]:
        circ = decompose(build_target(12, 6, "high", "high", book, "low"))
        b, trunc = mps_bond_log2(12, circ)
        tw, tw_exact = treewidth_log2(12, circ)
        print(f"  generado {tag:>4}: MPS bond REAL = 2^{b:.2f}{' (truncado)' if trunc else ''} | "
              f"treewidth {'EXACTO' if tw_exact else 'heuristico'} = 2^{tw:.2f}")
    print("\n  (el arsenal daba MPS 2^0 para 'core' por saltar los rz en cx-rz-cx; quimb lo mide bien.)")
    print("DONE")


if __name__ == "__main__":
    main()

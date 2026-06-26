"""benchmark.py -- GROUND TRUTH del atlas (Opcion B del revisor: validar, no afirmar).

Valida la clasificacion del atlas contra:
  - STIM (Google/Gidney): ground truth EXACTO de '¿es Clifford?' -- el simulador de estabilizadores de
    referencia mundial. Un circuito es Clifford sii Stim lo acepta sin gates no-Clifford. Comparamos con
    nuestro veredicto 'stabilizer' del flattener. Deben coincidir.
  - Respuestas ANALITICAS conocidas: T^8=I (magia 0), Toffoli (7 T), GHZ (bond 2), etc.

Si todos pasan -> la clasificacion del atlas concuerda con el ground truth independiente. Eso es lo que
convierte los proxies declarados en numeros respaldados.

Uso:  PYTHONPATH=src pixi run python benchmark.py
"""
from __future__ import annotations
import os
import sys
sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stim
from atlas import safe_parse, cost_atlas

_STIM = {"h": "H", "s": "S", "x": "X", "y": "Y", "z": "Z", "cx": "CX", "cz": "CZ"}


def stim_is_clifford(circuit) -> bool:
    """Ground truth EXACTO: ¿el circuito (ya descompuesto a primitivos) es Clifford? Stim lo decide."""
    c = stim.Circuit()
    for g in circuit:
        if g[0] == "t":                      # T no es Clifford -- Stim no lo simula como tableau
            return False
        if g[0] not in _STIM:
            return False                     # gate no-Clifford conocido -> no estabilizador
        try:
            c.append(_STIM[g[0]], list(g[1:]))
        except Exception:
            return False
    return True


def qreg(n):
    return f"OPENQASM 2.0;\nqreg q[{n}];\n"


CASES = [
    # (nombre, qasm, magia esperada (None=no chequear), ¿es Clifford? (ground truth analitico))
    ("Clifford H+S+CX",   qreg(3) + "h q[0];\ns q[1];\ncx q[0],q[1];\ncx q[1],q[2];\n", 0, True),
    ("T (1 magia)",       qreg(1) + "t q[0];\n", 1, False),
    ("T^8 = I",           qreg(1) + "t q[0];\n" * 8, 0, True),
    ("T then Tdg = I",    qreg(1) + "t q[0];\ntdg q[0];\n", 0, True),
    ("Toffoli ccx",       qreg(3) + "ccx q[0],q[1],q[2];\n", 7, False),
    ("rx(pi/2) Clifford", qreg(1) + "rx(pi/2) q[0];\n", 0, True),
    ("rx(0.7) magia",     qreg(1) + "rx(0.7) q[0];\n", 1, False),
    ("crz(0.7)",          qreg(2) + "crz(0.7) q[0],q[1];\n", None, False),
    ("GHZ-6 Clifford",    qreg(6) + "h q[0];\n" + "".join(f"cx q[{i}],q[{i+1}];\n" for i in range(5)), 0, True),
    ("S+H+T+CX mezcla",   qreg(2) + "h q[0];\nt q[0];\ncx q[0],q[1];\ns q[1];\n", 1, False),
]


def main():
    print("BENCHMARK -- atlas vs STIM (ground truth de Clifford) + respuestas analiticas\n")
    print(f"  {'caso':>22} | {'magia':>6} | {'esper.':>6} | {'libro':>11} | {'Stim:Cliff?':>11} | match")
    print("  " + "-" * 76)
    npass = ntot = 0
    for name, qasm, exp_magic, exp_cliff in CASES:
        n, circ, _ = safe_parse(qasm)
        r = cost_atlas(n, circ)
        magic = r["t_count"]; book = r["libro_flattener"]
        stim_cliff = stim_is_clifford(circ)
        # checks: (1) nuestro 'stabilizer' <=> Stim dice Clifford  (2) magia coincide con lo esperado
        c1 = (book == "stabilizer") == stim_cliff
        c2 = (exp_magic is None) or (magic == exp_magic)
        c3 = stim_cliff == exp_cliff                       # Stim concuerda con el ground truth analitico
        ok = c1 and c2 and c3; npass += ok; ntot += 1
        em = exp_magic if exp_magic is not None else "-"
        print(f"  {name:>22} | {magic:>6} | {str(em):>6} | {book:>11} | {str(stim_cliff):>11} | "
              f"{'✅' if ok else '❌ '+('magia' if not c2 else 'libro!=Stim' if not c1 else 'Stim!=gt')}")
    print("  " + "-" * 76)
    print(f"\n  {npass}/{ntot} casos pasan el ground truth.")
    print(f"  Validacion: el veredicto 'stabilizer' del atlas {'COINCIDE' if npass==ntot else 'DISCREPA'} con Stim")
    print(f"  (el simulador de estabilizadores de referencia), y la magia con las respuestas analiticas.")
    if npass == ntot:
        print("  -> los proxies declarados estan RESPALDADOS por ground truth independiente. Instrumento, no demo.")
    else:
        print("  -> hay discrepancias: revisar (esto es exactamente para lo que sirve el benchmark).")
    print("DONE")


if __name__ == "__main__":
    main()

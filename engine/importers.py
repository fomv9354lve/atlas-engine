"""importers.py -- multi-formato de ENTRADA. El ecosistema (Qiskit, Cirq, TKET) ya EXPORTA OpenQASM; el
unlock real es (a) aceptar objetos nativos y (b) que el QASM que emiten parsee aunque use compuertas que el
parser de atlas aun no maneja nativamente.

Dos caminos:
  - from_qiskit(qc) / from_cirq(circ): objeto nativo -> OpenQASM 2.0 (via su exportador propio, verificado).
  - normalize_qasm(text): RED DE SEGURIDAD. Si el QASM trae gates raros (ch, csx, cu3, mcx...), lo carga con
    Qiskit y lo re-transpila a una base que atlas SI maneja, preservando la dureza (magia + entrelazamiento).

Todo es opcional: si Qiskit/Cirq no estan instalados, las funciones lanzan ImportError y atlas sigue con su
parser nativo. No anaden dependencia dura.
"""
from __future__ import annotations

# Base de gates que el parser de atlas maneja NATIVAMENTE (preserva estructura -> mejor deteccion de libro).
_ATLAS_BASIS = ["u", "cx", "swap", "cz", "cy", "rzz", "rxx", "ryy", "crx", "cry", "crz",
                "ccx", "cswap", "h", "rz", "rx", "ry", "t", "tdg", "s", "sdg", "x", "y", "z", "sx", "id"]


def from_qiskit(qc) -> str:
    """qiskit.QuantumCircuit -> OpenQASM 2.0. Transpila a la base de atlas (decompone lo que no este en ella)."""
    from qiskit import transpile
    from qiskit.qasm2 import dumps
    try:
        tq = transpile(qc, basis_gates=_ATLAS_BASIS, optimization_level=0)
    except Exception:
        tq = transpile(qc, basis_gates=["u", "cx"], optimization_level=0)   # base minima garantizada
    return dumps(tq)


def from_cirq(circ) -> str:
    """cirq.Circuit -> OpenQASM 2.0 (exportador nativo de Cirq)."""
    return circ.to_qasm()


def from_pytket(circ) -> str:
    """pytket.Circuit -> OpenQASM 2.0 (exportador nativo de TKET). Requiere pytket instalado."""
    from pytket.qasm import circuit_to_qasm_str
    return circuit_to_qasm_str(circ)


def from_braket(circ) -> str:
    """braket.circuits.Circuit -> OpenQASM 3.0 (IR nativo de Braket). Requiere amazon-braket-sdk instalado.
    atlas ingiere 3.0, asi que esto entra directo."""
    try:
        from braket.circuits.serialization import IRType
        return circ.to_ir(ir_type=IRType.OPENQASM).source
    except Exception:
        return circ.to_ir().source                          # fallback API antigua


def normalize_qasm(text: str) -> str:
    """Red de seguridad: carga el QASM con Qiskit y lo reescribe a la base de atlas. Lanza ImportError si
    no hay Qiskit, o ValueError si Qiskit no puede leer el texto."""
    try:
        from qiskit import QuantumCircuit, transpile
        from qiskit.qasm2 import dumps, loads
    except ImportError as e:
        raise ImportError("Qiskit no disponible para normalizar") from e
    try:
        try:
            qc = loads(text)                                  # qasm2 estandar
        except Exception:
            qc = QuantumCircuit.from_qasm_str(text)           # fallback (API vieja / qasm con quirks)
    except Exception as e:
        raise ValueError(f"Qiskit no pudo leer el QASM: {type(e).__name__}: {e}") from e
    try:
        tq = transpile(qc, basis_gates=_ATLAS_BASIS, optimization_level=0)
    except Exception:
        tq = transpile(qc, basis_gates=["u", "cx"], optimization_level=0)
    return dumps(tq)


def qiskit_available() -> bool:
    try:
        import qiskit  # noqa: F401
        return True
    except ImportError:
        return False

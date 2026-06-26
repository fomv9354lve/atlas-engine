"""atlas_variational.py -- VARIATIONAL TRIAGE para Atlas (cierra el hueco hostil #10 / Part3: VQE/QAOA).

El problema: atlas.cost_atlas(n, circ) cuesta UN circuito concreto. Pero los casos de uso REALES de QPU
(VQE, QAOA) no son un circuito: son un MISMO ansatz parametrizado evaluado MILES de veces dentro de un
bucle de optimizacion clasico (un punto de parametros por evaluacion). El coste relevante no es el de un
disparo sino el PRESUPUESTO TOTAL = (coste-por-disparo) x (#evaluaciones).

Lo que este modulo SI mide (apoyado en cost_atlas, que es ground-truth via Stim/quimb/cotengra):
  - El coste-por-disparo de simular clasicamente UN binding concreto del ansatz (reusa cost_atlas).
  - Robustez de ese coste a traves de varios bindings aleatorios (el coste de simulacion clasica de un
    ansatz NO depende del valor de los angulos: la estructura -- #T, entanglement, treewidth -- es la misma;
    lo verificamos empiricamente con varios bindings y AVISAMOS si difieren).
  - El presupuesto clasico total = coste-por-disparo x n_params x n_iters (evaluaciones de funcion).
  - Una comparacion HONESTA contra un presupuesto de disparos de QPU (shots x evaluaciones), expresada como
    "¿cabe la simulacion clasica del ansatz en RAM/tiempo?" -- es decir, ¿necesitas QPU para evaluar este
    ansatz, o un laptop lo resuelve?

Lo que este modulo NO PUEDE medir y NO finge (lo declara como heuristica/desconocido):
  - Barren plateaus / entrenabilidad: si el gradiente se desvanece exponencialmente con n, el bucle clasico
    NO converge -- pero eso es un problema de OPTIMIZACION, no de coste-por-disparo, y predecirlo en general
    es un area de investigacion ABIERTA (Cerezo et al., "Cost function dependent barren plateaus in shallow
    parametrized quantum circuits", Nat. Commun. 2021; McClean et al. 2018). Damos solo BANDERAS heuristicas
    (profundidad/expresividad del ansatz, ansatz global vs local) -- NUNCA un veredicto de entrenabilidad.
  - Rugosidad del paisaje / #iteraciones reales hasta converger: n_iters es una ENTRADA del usuario, no algo
    que midamos. El optimizador real puede necesitar mas (o menos).
  - Ventaja cuantica: que la simulacion clasica del ansatz sea cara NO implica que la QPU sea util ni mas
    barata; el ruido de la QPU (vease atlas noise model) puede destruir la senal. Esto solo decide "¿hace
    falta una QPU para EVALUAR el ansatz, o lo simula un clasico?", nunca "la QPU dara ventaja".

API:
    variational_triage(builder_or_qasm, n_params, n_iters, ...)
        builder_or_qasm:
          - callable(theta: np.ndarray) -> (n, circuit)   # constructor de ansatz (theta de longitud n_params)
          - str con OpenQASM que contiene parametros simbolicos {p0, p1, ...} o angulos a sustituir
        -> dict con per_shot, total_classical_sim, qpu_shot_budget, comparison, trainability_flags (heuristico)

    qaoa_builder(n, p, edges) -> builder            # ansatz QAOA p-capas para MaxCut sobre 'edges'
    hardware_efficient_builder(n, layers)           # ansatz VQE hardware-efficient (Ry + CX entangling)

Reusa atlas.cost_atlas y atlas.safe_parse. Ejecutar:
    PYTHONPATH=. NUMBA_DISABLE_JIT=1 python3 atlas_variational.py
"""
from __future__ import annotations
import math
import numpy as np

from atlas import cost_atlas, safe_parse


# ============================================================ CONSTRUCTORES DE ANSATZ (builders)
def _qasm_header(n):
    return ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{n}];"]


def qaoa_builder(n: int, p: int, edges):
    """Ansatz QAOA de p capas para MaxCut sobre 'edges' (lista de (i,j)). 2p parametros (gamma_l, beta_l).

    Cada capa: e^{-i gamma H_C} (ZZ por arista via cx-rz-cx) seguido de e^{-i beta H_B} (rx por qubit).
    Devuelve un builder(theta) -> (n, qasm_str). Emitimos OpenQASM (con rz/rx) y dejamos que atlas.safe_parse
    lo descomponga a su base primitiva -- es la MISMA ruta de descomposicion honesta que usa todo atlas, y
    evita el limite de la propagacion de Pauli del motor (que no entiende rz/rx directos)."""
    edges = [tuple(e) for e in edges]

    def build(theta):
        theta = np.asarray(theta, float).ravel()
        if theta.size != 2 * p:
            raise ValueError(f"QAOA p={p} requiere {2*p} parametros (gamma_l,beta_l), recibidos {theta.size}")
        lines = _qasm_header(n)
        lines += [f"h q[{q}];" for q in range(n)]            # estado inicial |+>^n
        for L in range(p):
            gamma, beta = float(theta[2 * L]), float(theta[2 * L + 1])
            for (i, j) in edges:                            # e^{-i gamma Z_i Z_j} = CX Rz(2gamma) CX
                lines += [f"cx q[{i}],q[{j}];", f"rz({2.0*gamma}) q[{j}];", f"cx q[{i}],q[{j}];"]
            for q in range(n):                              # e^{-i beta X_q} = Rx(2beta)
                lines.append(f"rx({2.0*beta}) q[{q}];")
        return n, "\n".join(lines) + "\n"

    build.n_params = 2 * p
    build.label = f"QAOA(n={n}, p={p}, |E|={len(edges)})"
    return build


def hardware_efficient_builder(n: int, layers: int, entangler="linear"):
    """Ansatz VQE 'hardware-efficient': por capa, Ry(theta) en cada qubit + escalera de CX. n*layers params.
    Devuelve un builder(theta) -> (n, qasm_str). entangler: 'linear' (cadena CX) o 'full' (todos los pares)."""
    def build(theta):
        theta = np.asarray(theta, float).ravel()
        need = n * layers
        if theta.size != need:
            raise ValueError(f"HEA n={n},layers={layers} requiere {need} params, recibidos {theta.size}")
        lines = _qasm_header(n)
        k = 0
        for L in range(layers):
            for q in range(n):
                lines.append(f"ry({float(theta[k])}) q[{q}];"); k += 1
            if entangler == "full":
                for i in range(n):
                    for j in range(i + 1, n):
                        lines.append(f"cx q[{i}],q[{j}];")
            else:                                            # linear
                for q in range(n - 1):
                    lines.append(f"cx q[{q}],q[{q+1}];")
        return n, "\n".join(lines) + "\n"

    build.n_params = n * layers
    build.label = f"HEA(n={n}, layers={layers}, {entangler})"
    return build


# ============================================================ NORMALIZACION DE ENTRADA QASM-CON-PARAMETROS
def _qasm_param_builder(qasm_text: str):
    """Convierte un QASM con marcadores de parametro '{p0}','{p1}',... en un builder(theta)->(n,circuit).

    HONESTO: solo soporta el formato de marcador con llaves (p.ej. 'rz({p0}) q[0];'). Para QASM con
    parametros simbolicos de OpenQASM 3 ('input angle p0;') NO hay sustitucion automatica: avisamos y
    el usuario debe pasar un builder. Cuenta los marcadores distintos como n_params."""
    import re
    markers = sorted(set(re.findall(r"\{p(\d+)\}", qasm_text)), key=int)
    n_params = (max(int(m) for m in markers) + 1) if markers else 0

    def build(theta):
        theta = np.asarray(theta, float).ravel()
        txt = qasm_text
        for m in markers:
            txt = txt.replace("{p" + m + "}", repr(float(theta[int(m)])))
        # devolvemos el QASM ya sustituido; _cost_binding lo parsea (uniforme con los builders QAOA/VQE)
        return None, txt

    build.n_params = n_params
    build.label = "QASM-parametrizado"
    build._markers = markers
    return build


def _resolve_builder(builder_or_qasm, n_params):
    """Devuelve (builder, n_params, source_label, extra_warnings)."""
    warns = []
    if callable(builder_or_qasm):
        b = builder_or_qasm
        np_ = getattr(b, "n_params", n_params)
        if n_params is not None and np_ is not None and n_params != np_:
            warns.append(f"n_params={n_params} difiere del declarado por el builder ({np_}); uso {np_}")
        return b, (np_ if np_ is not None else n_params), getattr(b, "label", "builder"), warns
    if isinstance(builder_or_qasm, str):
        b = _qasm_param_builder(builder_or_qasm)
        if b.n_params == 0:
            warns.append("el QASM no contiene marcadores {p0},{p1},...: se tratara como circuito FIJO "
                         "(sin parametros). Si tu QASM usa parametros simbolicos de OpenQASM3, pasa un builder.")
            np_eff = n_params if n_params else 0
        else:
            np_eff = b.n_params
            if n_params is not None and n_params != b.n_params:
                warns.append(f"n_params={n_params} difiere de los marcadores hallados ({b.n_params}); uso {b.n_params}")
        return b, np_eff, "QASM-parametrizado", warns
    raise TypeError("builder_or_qasm debe ser callable(theta)->(n,circuit) o un str QASM")


def _materialize(builder, theta):
    """Llama al builder y devuelve (n, circuit_lista). Acepta builders que devuelven (n, lista_de_tuplas) O
    (n, qasm_str): los QASM se parsean con atlas.safe_parse (misma descomposicion honesta que todo atlas).
    Si n es None (el builder solo dio QASM), lo toma del parseo."""
    n, payload = builder(theta)
    if isinstance(payload, str):
        pn, circ, _ = safe_parse(payload)
        return (pn if n is None else n), circ
    return n, payload


def _cost_binding(builder, theta, budget_log2, warns):
    """Costea UN binding con atlas.cost_atlas. Devuelve (n, atlas_result_dict) o (n, None) si falla."""
    try:
        n, circ = _materialize(builder, theta)
    except Exception as e:
        warns.append(f"binding fallo al construirse: {type(e).__name__}: {e}")
        return None, None
    try:
        return n, cost_atlas(n, circ, budget_log2=budget_log2)
    except Exception as e:
        warns.append(f"cost_atlas fallo en un binding (n={n}): {type(e).__name__}: {e}")
        return n, None


# ============================================================ BANDERAS DE ENTRENABILIDAD (HEURISTICAS, NO VEREDICTO)
def _trainability_flags(n, n_params, circuit, ansatz_label):
    """Banderas HEURISTICAS sobre entrenabilidad. NO es un veredicto: la prediccion de barren plateaus en
    general es un problema ABIERTO (Cerezo et al. 2021). Solo levantamos banderas de RIESGO conocidas y las
    etiquetamos como heuristica/desconocido. Devuelve dict con 'status'='heuristic_only'."""
    depth_2q = sum(1 for g in circuit if g and g[0] in ("cx", "cnot", "cz"))
    flags = []
    # Riesgo 1: ansatz profundo + muchos qubits -> el resultado de McClean 2018 (varianza del gradiente
    # ~ exp(-n)) aplica a ansatze aleatorios profundos (2-disenos aprox). Heuristica: n grande Y profundo.
    if n >= 12 and depth_2q >= 2 * n:
        flags.append(f"ansatz profundo (n={n}, {depth_2q} puertas-2q): RIESGO de barren plateau si el ansatz "
                     f"se aproxima a un 2-diseno (McClean 2018). HEURISTICO -- no medimos la varianza real.")
    # Riesgo 2: muchos parametros respecto a n -> sobre-parametrizacion (puede ayudar O perjudicar; abierto).
    if n_params > 4 * n:
        flags.append(f"n_params={n_params} >> n={n}: regimen sobre-parametrizado; el paisaje puede ser benigno "
                     f"(Larocca 2023) O plano -- DESCONOCIDO sin medir el paisaje. HEURISTICO.")
    # Riesgo 3: costo global (no lo sabemos sin el observable) -- avisamos del eje, no lo decidimos.
    flags.append("entrenabilidad (gradiente desvaneciente / rugosidad / #iters-hasta-converger): NO MEDIDO. "
                 "Es un area de investigacion abierta (Cerezo et al., Nat.Commun. 2021); n_iters es una "
                 "ENTRADA tuya, no una prediccion nuestra.")
    return {"status": "heuristic_only", "ansatz": ansatz_label, "depth_2q_per_binding": depth_2q,
            "flags": flags,
            "disclaimer": "Estas banderas NO predicen convergencia. Solo el coste-por-disparo y el "
                          "presupuesto total estan respaldados por ground-truth (Stim/quimb/cotengra)."}


# ============================================================ EL TRIAGE
def variational_triage(builder_or_qasm, n_params=None, n_iters=100, *,
                       shots_per_eval=1024, n_bindings=3, budget_log2=40.0,
                       ram_budget_bytes=24e9, seed=0):
    """Triage variacional: cuesta el ansatz parametrizado a traves del bucle de optimizacion completo.

    Parametros
    ----------
    builder_or_qasm : callable(theta)->(n,circuit)  O  str QASM con marcadores {p0},{p1},...
    n_params        : #parametros del ansatz (si el builder no lo declara). En QAOA p-capas = 2p.
    n_iters         : #iteraciones del optimizador clasico (ENTRADA del usuario; no la predecimos).
    shots_per_eval  : disparos por evaluacion de funcion en la QPU (para el presupuesto de disparos QPU).
    n_bindings      : #bindings aleatorios para verificar que el coste-por-disparo NO depende de los angulos.
    budget_log2     : presupuesto de coste clasico (log2 amplitudes) que define WALL en cost_atlas.
    ram_budget_bytes: RAM clasica disponible (default 24 GB del M4 de referencia).

    Devuelve
    -------
    dict con:
      n, n_params, n_iters, ansatz, n_evaluations (= n_params*n_iters para gradiente por diferencias finitas,
        o n_iters si se usa gradiente analitico/sin gradiente),
      per_shot: coste-por-disparo de UN binding (veredicto de atlas: union_cost_log2, best_method, route,
                resources, t_count, n_2q, confidence) + estabilidad a traves de bindings,
      total_classical_sim: presupuesto clasico total (tiempo y si cabe el bucle en un horizonte razonable),
      qpu_shot_budget: #disparos totales en QPU,
      comparison: recomendacion HONESTA (simula-en-clasico vs candidato-a-QPU), con caveats,
      trainability: banderas heuristicas (NO veredicto),
      warnings: lista de avisos.
    """
    rng = np.random.default_rng(seed)
    builder, n_params, label, warns = _resolve_builder(builder_or_qasm, n_params)
    if not n_params or n_params < 1:
        n_params = 1
        warns.append("n_params indeterminado o 0: asumo 1 (circuito casi-fijo). El presupuesto total puede "
                     "estar sub-estimado si el ansatz tiene parametros que no detecte.")

    # ---- 1) Coste-por-disparo: costea varios bindings aleatorios y verifica estabilidad estructural.
    per_binding = []
    n_seen = None
    for _ in range(max(1, n_bindings)):
        theta = rng.uniform(0.0, 2.0 * math.pi, size=n_params)
        n, r = _cost_binding(builder, theta, budget_log2, warns)
        n_seen = n
        if r is None:
            continue
        ra = r.get("route_adjudication") or {}
        per_binding.append({
            "union_cost_log2": r.get("union_cost_log2"),
            "best_method": r.get("best_method"),
            "tractable": r.get("tractable"),
            "verdict": r.get("verdict"),
            "route": ra.get("route"),
            "governing_cost_log2": ra.get("governing_cost_log2"),
            "confidence": ra.get("confidence"),
            "resources": r.get("resources"),
            "t_count": r.get("t_count"),
            "n_2q": r.get("n_2q"),
            "noise": r.get("noise"),
        })

    if not per_binding:                                    # todos los bindings fallaron al costearse
        return {
            "ansatz": label, "n": n_seen, "n_params": n_params, "n_iters": n_iters,
            "per_shot": None, "total_classical_sim": None, "qpu_shot_budget": None,
            "comparison": {"recommendation": "OOD / VERIFICAR",
                           "rationale": "ningun binding del ansatz se pudo costear (fuera de la base "
                                        "soportada o error de ground-truth). Revisa los avisos.",
                           "caveats": []},
            "trainability": {"status": "heuristic_only", "flags": [], "ansatz": label},
            "warnings": warns,
        }
    costs = [b["union_cost_log2"] for b in per_binding if isinstance(b["union_cost_log2"], (int, float))]
    routes = set(b["route"] for b in per_binding)
    stable = (len(set(round(c, 1) for c in costs)) <= 1) and (len(routes) <= 1)
    if not stable:
        warns.append("el coste-por-disparo VARIO entre bindings (costs_log2="
                     f"{[round(c,2) for c in costs]}, routes={routes}). Esto es inusual (la estructura del "
                     "ansatz suele fijar la dureza); reporto el PEOR caso (mas caro) por seguridad.")
    # peor caso (mas caro) como representante del coste-por-disparo
    rep = max(per_binding, key=lambda b: (b["union_cost_log2"] if isinstance(b["union_cost_log2"], (int, float)) else -1))
    per_shot_ram = (rep["resources"] or {}).get("ram_bytes")
    per_shot_time_s = (rep["resources"] or {}).get("time_s")

    # ---- 2) #evaluaciones. Por defecto: gradiente por diferencias finitas o parameter-shift => ~2 evals
    # por parametro por iteracion. Reportamos ambas convenciones para honestidad.
    evals_param_shift = 2 * n_params * n_iters            # parameter-shift: 2 circuitos por parametro
    evals_gradient_free = n_iters                          # optimizador sin gradiente (1 eval/iter, idealizado)
    n_evaluations = evals_param_shift                      # convencion por defecto (la mas comun en VQE/QAOA)

    # ---- 3) Presupuesto clasico total = coste-por-disparo x #evaluaciones.
    # En tiempo: cada evaluacion es una simulacion completa del circuito (per_shot_time_s).
    total_time_s = (per_shot_time_s * n_evaluations) if isinstance(per_shot_time_s, (int, float)) else None
    # En log2-amplitudes el coste por-disparo NO se suma (cada eval es independiente); el RAM pico es el de
    # UN disparo. Lo que escala con #evals es el TIEMPO, no la RAM.
    total_classical = {
        "n_evaluations_parameter_shift": evals_param_shift,
        "n_evaluations_gradient_free": evals_gradient_free,
        "n_evaluations_used": n_evaluations,
        "per_eval_ram_bytes": per_shot_ram,
        "per_eval_time_s": per_shot_time_s,
        "peak_ram_bytes": per_shot_ram,                    # pico = un disparo (evals son secuenciales)
        "peak_ram_fits_budget": (per_shot_ram is not None and per_shot_ram <= ram_budget_bytes),
        "total_wallclock_time_s": round(total_time_s, 4) if total_time_s is not None else None,
        "total_wallclock_human": _human_time(total_time_s),
        "note": "RAM pico = coste de UN disparo (las evaluaciones son secuenciales); lo que crece con "
                "#evaluaciones es el TIEMPO de pared, no la RAM. per-eval-time es estimacion de orden de "
                "magnitud (ancho de banda de memoria), NO un benchmark medido.",
    }

    # ---- 4) Presupuesto de disparos QPU (para contexto, NO una recomendacion de comprar).
    qpu_shots = shots_per_eval * n_evaluations
    qpu_shot_budget = {
        "shots_per_eval": shots_per_eval,
        "total_shots": qpu_shots,
        "note": "disparos totales si se ejecutara en QPU. No incluye tiempo de cola, recompilacion/SWAP, "
                "ni mitigacion de error -- y NO implica que la QPU sea necesaria o ventajosa.",
    }

    # ---- 5) Recomendacion HONESTA. Solo decidimos 'simula-en-clasico' (fuerte) vs 'candidato-defer'.
    comparison = _recommend(rep, total_classical, n_seen, budget_log2, ram_budget_bytes)

    # ---- 6) Banderas de entrenabilidad (heuristicas). Usamos el circuito del binding representante.
    _, rep_circ = _materialize(builder, rng.uniform(0, 2 * math.pi, size=n_params))
    trainability = _trainability_flags(n_seen, n_params, rep_circ, label)

    return {
        "ansatz": label,
        "n": n_seen,
        "n_params": n_params,
        "n_iters": n_iters,
        "per_shot": {
            "representative": rep,
            "all_bindings": per_binding,
            "structurally_stable_across_bindings": stable,
            "note": "el coste-por-disparo es el de UN circuito concreto (ground-truth via atlas). La "
                    "estructura del ansatz (no los angulos) fija la dureza; verificamos con varios bindings.",
        },
        "total_classical_sim": total_classical,
        "qpu_shot_budget": qpu_shot_budget,
        "comparison": comparison,
        "trainability": trainability,
        "warnings": warns,
    }


def _human_time(t_s):
    if t_s is None:
        return None
    for u, d in [(86400.0, "d"), (3600.0, "h"), (60.0, "min"), (1.0, "s"), (1e-3, "ms"), (1e-6, "us")]:
        if t_s >= u:
            return f"{t_s/u:.2f} {d}"
    return f"{t_s*1e9:.0f} ns"


def _recommend(rep, total_classical, n, budget_log2, ram_budget_bytes):
    """Recomendacion honesta. FUERTE solo al decir 'simula en clasico' (atlas exhibe un metodo). Para el
    otro lado solo 'candidato-defer' (probar necesidad de QPU = BQP!=BPP, no demostrable)."""
    tractable = rep.get("tractable")
    fits = total_classical["peak_ram_fits_budget"]
    cost = rep.get("union_cost_log2")
    if tractable is True and fits:
        rec = "SIMULA-EN-CLASICO"
        rationale = (f"cada evaluacion del ansatz es clasicamente tratable (via {rep.get('best_method')}, "
                     f"2^{cost}, cabe en RAM): atlas EXHIBE un metodo clasico. NO necesitas una QPU para "
                     f"EVALUAR este ansatz. (No afirmamos nada sobre convergencia del optimizador.)")
    elif tractable is False:
        rec = "CANDIDATO-DEFER (QPU)"
        rationale = (f"el coste-por-evaluacion excede el presupuesto clasico (WALL: 2^{cost} > 2^{int(budget_log2)} "
                     f"o no cabe en RAM) para TODOS los metodos medidos. Esto es un CANDIDATO a QPU, NO una "
                     f"prueba de que la QPU sea necesaria (probar necesidad = BQP!=BPP, abierto) ni ventajosa "
                     f"(el ruido de la QPU puede destruir la senal). Verifica con hardware.")
    elif tractable is None:
        rec = "PROVISIONAL"
        rationale = (f"el mejor metodo clasico es MPS TRUNCADO (cota inferior 2^{cost}); la tratabilidad NO "
                     f"esta confirmada. No concluimos sin un binding exacto o mas bond.")
    else:
        rec = "OOD / VERIFICAR"
        rationale = "no se pudo costear el ansatz (fuera de la base soportada o error de ground-truth)."
    if tractable is True and not fits:
        rec = "CANDIDATO-DEFER (RAM)"
        rationale = (f"el metodo clasico existe (2^{cost}) pero su RAM pico no cabe en el presupuesto "
                     f"({ram_budget_bytes/1e9:.0f} GB). Tratable en una maquina mayor; candidato a QPU solo si "
                     f"no hay tal maquina. No es prueba de ventaja cuantica.")
    return {
        "recommendation": rec,
        "rationale": rationale,
        "per_eval_tractable": tractable,
        "per_eval_fits_ram": fits,
        "caveats": [
            "Esto decide si necesitas QPU para EVALUAR el ansatz, NO si la QPU dara VENTAJA.",
            "n_iters es tu entrada; el optimizador real puede necesitar mas/menos (no lo predecimos).",
            "No incluye tiempo de cola de QPU, recompilacion/SWAP, ni mitigacion de error.",
            "Asume que el mejor metodo clasico medido (a menudo MPS) es representativo; treewidth es cota "
            "superior greedy y MPS puede ser cota inferior truncada (vease atlas exact_verification).",
        ],
    }


# ============================================================ DEMO
def _demo():
    print("=" * 78)
    print("atlas_variational.py -- VARIATIONAL TRIAGE (demo)")
    print("=" * 78)

    # QAOA p=2 para MaxCut en un anillo de 6 nodos (caso de uso QPU clasico).
    n = 6
    edges = [(i, (i + 1) % n) for i in range(n)]            # anillo
    builder = qaoa_builder(n, p=2, edges=edges)
    print(f"\nAnsatz: {builder.label}, edges(anillo)={edges}")
    print(f"n_params = {builder.n_params} (= 2p), n_iters = 80, shots/eval = 1024\n")

    out = variational_triage(builder, n_params=builder.n_params, n_iters=80,
                             shots_per_eval=1024, n_bindings=3)

    rep = out["per_shot"]["representative"]
    print("--- COSTE POR DISPARO (un binding, ground-truth via atlas) ---")
    print(f"  veredicto      : {rep['verdict']}")
    print(f"  mejor metodo   : {rep['best_method']}  (2^{rep['union_cost_log2']})")
    print(f"  ruta           : {rep['route']}  | confianza: {(rep['confidence'] or {}).get('label')} "
          f"({(rep['confidence'] or {}).get('score')})")
    print(f"  #T={rep['t_count']}  #2q={rep['n_2q']}  RAM/eval={ (rep['resources'] or {}).get('ram_human') }")
    print(f"  estable entre bindings: {out['per_shot']['structurally_stable_across_bindings']}")

    tc = out["total_classical_sim"]
    print("\n--- PRESUPUESTO CLASICO TOTAL (bucle completo) ---")
    print(f"  #evaluaciones (parameter-shift, 2*n_params*n_iters): {tc['n_evaluations_parameter_shift']}")
    print(f"  RAM pico (= 1 disparo, evals secuenciales): {(rep['resources'] or {}).get('ram_human')} "
          f"-> cabe: {tc['peak_ram_fits_budget']}")
    print(f"  tiempo de pared estimado (orden de magnitud): {tc['total_wallclock_human']}")

    print("\n--- PRESUPUESTO DE DISPAROS QPU (contexto, no recomendacion) ---")
    print(f"  disparos totales: {out['qpu_shot_budget']['total_shots']:,}")

    cmp = out["comparison"]
    print("\n--- RECOMENDACION (honesta) ---")
    print(f"  >> {cmp['recommendation']}")
    print(f"     {cmp['rationale']}")

    print("\n--- ENTRENABILIDAD (heuristico -- NO veredicto) ---")
    print(f"  status: {out['trainability']['status']}")
    for f in out["trainability"]["flags"]:
        print(f"   ! {f}")

    if out["warnings"]:
        print("\n--- AVISOS ---")
        for w in out["warnings"]:
            print(f"   ! {w}")

    # Segundo demo: HEA mas grande (n=16) para mostrar el fast-path y un ansatz mas profundo.
    print("\n" + "=" * 78)
    b2 = hardware_efficient_builder(16, layers=3, entangler="linear")
    print(f"Ansatz: {b2.label}, n_params={b2.n_params}, n_iters=50")
    out2 = variational_triage(b2, n_params=b2.n_params, n_iters=50, n_bindings=2)
    rep2 = out2["per_shot"]["representative"]
    print(f"  veredicto: {rep2['verdict']}")
    print(f"  ruta: {rep2['route']} | RAM/eval: {(rep2['resources'] or {}).get('ram_human')}")
    print(f"  >> {out2['comparison']['recommendation']}: {out2['comparison']['rationale']}")
    for f in out2["trainability"]["flags"]:
        print(f"   ! {f}")


if __name__ == "__main__":
    _demo()

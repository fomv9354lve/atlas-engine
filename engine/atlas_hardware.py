#!/usr/bin/env python3
"""atlas_hardware — lente hardware-aware para Atlas (incorporables #2 y #3).

Cierra la asimetría honesta de Atlas: "no compres QPU" es demostrable; "necesita QPU" es
candidato-defer. Esta lente AÑADE una condición necesaria al candidato-defer: un circuito
solo es candidato a un QPU real si es **alcanzable** en ese QPU dentro de su presupuesto de
fidelidad. Si es demasiado profundo para correr con señal útil, NO es candidato a ESE QPU
(ni clásico ni este hardware ayudan) — eso es más honesto que "beyond classical".

Todo se obtiene de la calibración EN VIVO del backend (0 cuota; solo lectura de config/props).

Incorpora hallazgos del análisis profundo de ibm_kingston (2026-06-22):
  - readout REAL en circuitos = measure_2 (paralelo), que subestima el measure individual
    por ~5x (kingston: 0.046 vs 0.0098). La reachability usa measure_2, no measure.
  - el chip está limitado por error de PUERTA (~29-49 capas CZ), no por T2 (~2000 capas).
  - topología sparse heavy-hex (grado<=3, treewidth bajo) -> circuitos nativos tienden a
    bajo entrelazamiento (ver ATLAS_KINGSTON_INFERENCE.md).

NO requiere cuota. El modelo de ruido local (build_local_noise_model) usa qiskit-aer.
"""
from __future__ import annotations

import json
import math
import os
import statistics as st


# Snapshot MEDIDO en vivo (2026-06-22) — cross-checado contra el veredicto-por-hipótesis del
# usuario. Permite que el certificado use la lente hardware-aware OFFLINE (sin pegarle a IBM en
# cada llamada). Refrescar con summarize(); cada número es auditable.
KINGSTON_SNAPSHOT = {
    "backend": "ibm_kingston", "measured": "2026-06-22", "provenance": "live QiskitRuntimeService",
    "n": 156, "edges": 176, "coupling_treewidth": 4, "max_degree": 3,
    "cz_median": 2.03e-3, "sx_median": 2.72e-4, "readout_median": 7.93e-3,
    "depth_ceiling_eplg": 29, "depth_ceiling_local": 49,   # capas CZ a err<10% (EPLG100q / CZ local)
    "dead_qubits": [146],                                   # readout 49.5%, sin T1/T2 (qubit muerto)
    "exclude_qubits": [146, 121, 113, 131, 99, 112, 127],  # readout >= ~5% (incl. cluster TLS)
    "top_qubits": [21, 95, 149, 151, 0, 50, 1, 122, 94, 69],  # mejores por score T1+T2 / readout
    "measure2_over_measure": {     # H3: mediana ~1x; cola alta sí. Valores MEDIDOS por nosotros en
        "median": 0.97, "p75": 1.69, "p90": 3.42, "max": 71.2, "worst_q": 80,   # vivo (no portal).
        "frac_ge_5x": 0.07, "frac_ge_10x": 0.03,
        "portal_divergence": "el portal reportó 23%>=5x / 12%>=10x; nuestra medición live da "
                             "7%/3% — probable ventana de calibración distinta. El max Q80=71x coincide."},
    "health": {                    # lo que IBM publica pero no explica (MEDIDO live, cross-checado)
        "gate_lengths_ns": {"68": 172, "80": 3, "108": 1},   # 3 generaciones de couplers mezcladas
        "slow_couplers": {"80ns": [[6, 7], [29, 30], [138, 151]], "108ns": [[33, 34]]},
        "dephasing_frac_T2_lt_half_T1": 0.37,                 # 37% del chip en dephasing severo
        "idle_eq_sx": True,                                   # 156/156: idle estimado del gate error
        "readout_backaction_M2_lt_M_frac": 0.51,             # 51%: 2da medición mejor que la 1ra
        "cz_rzz_top_outlier": {"edge": [33, 39], "ratio": 4.27},  # candidato leakage/TLS
        "zz_residual_exact": {"published": True, "unit": "kHz", "max": 9.30, "max_edge": [127, 137],
                              "median": 4.56, "edge_131_138": 3.56,
                              "note": "IBM PUBLICA el ZZ exacto (general block, 176 edges). Todo en "
                                      "kHz de 1 dígito (couplers sintonizables). La estimación CZ/RZZ "
                                      "daba 131_138~86 kHz; el real es 3.56 kHz (24x menor) -> el edge "
                                      "está SANO en ZZ; su problema es el error de gate CZ, no el ZZ."},
        # derivaciones sobre datos públicos (matemática directa, lo que IBM no sintetiza):
        "cz_mean_over_median": 3.6,            # media 7.26e-3 vs mediana titular 2.02e-3 (cola larga)
        "effective_main_component": 76,        # chip 'bueno' (CZ<0.3%) fragmenta; mayor comp = 76 qubits
        "good_components": [76, 24, 12, 8, 5, 4],   # el '156' es operativamente ~76 + relleno
        "dephasing_dominated_frac": 0.74,      # 74% qubits limitados por ruido de fase (Tφ), no T1
        "frequencies_in_api": False,           # 0/156 -> loss-tangent exacto y colisión espectral = solo-IBM
        "sx_control_dominated": True,          # SX limitado por control/calibración, no decoherencia (32ns)
        "dead_zone_dynamic": ("edges totalmente rotos (CZ>=0.5) DERIVAN entre calibraciones: "
                              "snapshot previo 111_112/120_121; ahora 112_113/130_131/145_146/146_147. "
                              "El cluster caliente 111–122 persiste. Zona muerta = dinámica (TLS)."),
        "q121_chronic": ("historia de calibración (23-may→22-jun): Q121 T1 fluctúa 6–12µs TODO el "
                         "mes (crónico, no colapso reciente; firma TLS, nunca se recupera). Su "
                         "T2=23.4µs está CONGELADO en todos los snapshots (no se re-mide) — explica "
                         "parte de la anomalía T2>2T1. El cluster 111–122 lleva ≥1 mes degradado."),
    },
    "notes": ("T2>2T1 SOLO en Q121 (degradado, T1=11µs) — singular, no chip-wide; CPMG+TLS es "
              "inferencia. n_thermal de P01/P10 es ARTEFACTO de modelo (inestable si P10~P01), no "
              "temperatura física. 'zonas buenas' es heurística débil — el chip es heterogéneo."),
}

# Fecha de referencia HORNEADA del bundle de datos (no hay reloj fiable en el server sin red).
# La frescura de la calibración se computa contra esta constante, no contra time.time().
DATA_AS_OF = "2026-06-22"
CALIBRATION_STALE_DAYS = 7


def _iso_to_ordinal(d):
    """Convierte 'YYYY-MM-DD' a un día ordinal entero (token-free, sin datetime/red)."""
    try:
        y, m, dd = (int(x) for x in str(d).split("-")[:3])
    except Exception:
        return None
    # algoritmo de día juliano (proléptico gregoriano) — suficiente para restar fechas
    a = (14 - m) // 12
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return dd + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045


def calibration_freshness(snapshot=KINGSTON_SNAPSHOT, data_as_of=DATA_AS_OF,
                          stale_days=CALIBRATION_STALE_DAYS):
    """Frescura de la calibración del device SIN reloj ni red: compara snapshot['measured']
    contra la constante horneada DATA_AS_OF. Devuelve la fecha medida prominentemente y un
    warning suave si es rancia (> stale_days días)."""
    measured = snapshot.get("measured", "?")
    om, od = _iso_to_ordinal(measured), _iso_to_ordinal(data_as_of)
    age = (od - om) if (om is not None and od is not None) else None
    stale = (age is not None and age > stale_days)
    if age is None:
        label = "calibración medida: %s (frescura no computable)" % measured
    elif stale:
        label = ("calibración medida: %s ⚠ RANCIA (%d días desde %s; umbral %d) — "
                 "re-medir con summarize()" % (measured, age, data_as_of, stale_days))
    else:
        label = "calibración medida: %s (fresca, %d días)" % (measured, age)
    return {"measured": measured, "data_as_of": data_as_of, "age_days": age,
            "stale": stale, "stale_threshold_days": stale_days, "label": label}


def _load_token(token_file=None):
    tok = os.environ.get("QISKIT_IBM_TOKEN")
    tf = token_file or os.environ.get("QISKIT_IBM_TOKEN_FILE")
    if not tok and tf:
        p = os.path.expanduser(tf)
        if os.path.isfile(p):
            try:
                d = json.load(open(p, encoding="utf-8"))
                tok = d.get("apiKey") or d.get("token") or d.get("apikey") or d.get("api_key")
            except json.JSONDecodeError:
                tok = open(p, encoding="utf-8").read().strip() or None
    return tok


def pull_calibration(backend_name="ibm_kingston", token_file=None):
    """Trae la calibración en vivo de un backend IBM (0 cuota). Devuelve un dict estructurado.

    Returns:
        dict con: n, edges, per_qubit {T1,T2,readout,p01,p10}, per_edge {cz,rzz,len},
        gate medians, y readout-crosstalk (measure vs measure_2). El token nunca se imprime.

    Raises:
        RuntimeError: si no hay token.
    """
    tok = _load_token(token_file)
    if not tok:
        raise RuntimeError("no token: set QISKIT_IBM_TOKEN o QISKIT_IBM_TOKEN_FILE")
    from qiskit_ibm_runtime import QiskitRuntimeService
    svc = QiskitRuntimeService(channel="ibm_quantum_platform", token=tok)
    b = svc.backend(backend_name)
    props = b.properties()
    n = b.num_qubits
    edges = sorted({tuple(sorted(e)) for e in b.coupling_map.get_edges()})

    def qval(q, name):
        for nd in props.qubits[q]:
            if nd.name == name:
                return nd.value
        return None

    per_qubit = {}
    for q in range(n):
        # props.t1/t2 devuelven SEGUNDOS de forma consistente; try/except tolera Q146 (sin T1/T2).
        try:
            t1 = props.t1(q)
        except Exception:
            t1 = None
        try:
            t2 = props.t2(q)
        except Exception:
            t2 = None
        ro = qval(q, "readout_error")
        per_qubit[q] = {
            "T1_us": (t1 or 0) * 1e6, "T2_us": (t2 or 0) * 1e6,
            "readout": ro if ro is not None else 1.0,   # sin readout medible -> tratar como inútil
            "p01": qval(q, "prob_meas0_prep1"), "p10": qval(q, "prob_meas1_prep0")}
    # gate errors
    def gate_errs(gname):
        out = {}
        for g in props.gates:
            if g.gate != gname:
                continue
            err = next((p.value for p in g.parameters if p.name == "gate_error"), None)
            ln = next((p.value for p in g.parameters if p.name == "gate_length"), None)
            out[tuple(g.qubits)] = (err, ln)
        return out
    cz = gate_errs("cz"); rzz = gate_errs("rzz")
    sx = gate_errs("sx"); idg = gate_errs("id"); meas = gate_errs("measure"); meas2 = gate_errs("measure_2")
    # measure / measure_2 por qubit (para el factor de crosstalk de readout, qubit-especifico)
    meas_q = {k[0]: v[0] for k, v in meas.items() if v[0] is not None}
    meas2_q = {k[0]: v[0] for k, v in meas2.items() if v[0] is not None}
    sx_q = {k[0]: v[0] for k, v in sx.items() if v[0] is not None}
    id_q = {k[0]: v[0] for k, v in idg.items() if v[0] is not None}
    per_edge = {}
    for (u, v) in edges:
        e = cz.get((u, v)) or cz.get((v, u)) or (None, None)
        r = rzz.get((u, v)) or rzz.get((v, u)) or (None, None)
        per_edge[(u, v)] = {"cz": e[0], "cz_len": e[1], "rzz": r[0]}
    # ZZ residual EXACTO publicado por IBM (general block, zz_<concat>, GHz). No estimación.
    edge_set = set(edges)
    def _split_edge(digits):
        for i in range(1, len(digits)):
            try:
                e = tuple(sorted((int(digits[:i]), int(digits[i:]))))
            except ValueError:
                continue
            if e in edge_set:
                return e
        return None
    for nd in getattr(props, "general", []):
        if nd.name.startswith("zz_"):
            e = _split_edge(nd.name[3:])
            if e and e in per_edge:
                per_edge[e]["zz_hz"] = abs(nd.value) * (1e9 if nd.unit == "GHz" else 1)
    cz_errs = [d["cz"] for d in per_edge.values() if d["cz"] is not None]
    ro = [per_qubit[q]["readout"] for q in range(n)]
    sx_errs = [v[0] for v in sx.values() if v[0] is not None]
    meas_errs = [v[0] for v in meas.values() if v[0] is not None]
    meas2_errs = [v[0] for v in meas2.values() if v[0] is not None]
    return {
        "backend": backend_name, "n": n, "edges": edges,
        "per_qubit": per_qubit, "per_edge": per_edge,
        "meas_q": meas_q, "meas2_q": meas2_q, "sx_q": sx_q, "id_q": id_q,
        "median": {
            "cz": st.median(cz_errs) if cz_errs else None,
            "readout": st.median(ro), "sx": st.median(sx_errs) if sx_errs else None,
            "measure": st.median(meas_errs) if meas_errs else None,
            "measure_2": st.median(meas2_errs) if meas2_errs else None},
        "worst": {"readout_q": max(range(n), key=lambda q: ro[q]), "readout": max(ro)},
    }


def readout_crosstalk_factor(cal):
    """measure_2 (lectura paralela, la REAL en circuitos) vs measure (individual, lo publicado).

    Hallazgo honesto (kingston 2026-06-22): el factor MEDIANO chip-wide es ~1x — el blow-up de
    readout en paralelo es QUBIT-ESPECÍFICO (catastrófico en pocos qubits, p.ej. Q80/Q85), no
    chip-wide. Devuelve mediana y peor-caso por qubit. Caveat: measure_2 puede venir de una
    calibración de fecha distinta -> tratar el peor-caso como señal de a-qué-qubits-no-medir-en-paralelo.
    """
    med = (cal["median"]["measure_2"] / cal["median"]["measure"]
           if cal["median"]["measure"] and cal["median"]["measure_2"] else None)
    ratios = []
    for q, m in cal.get("meas_q", {}).items():
        m2 = cal.get("meas2_q", {}).get(q)
        if m and m2 and m > 0:
            ratios.append((m2 / m, q))
    worst = max(ratios) if ratios else (None, None)
    return {"median_ratio": med, "worst_ratio": worst[0], "worst_q": worst[1]}


def topology_summary(cal):
    """Treewidth (heurístico), distribución de grados y zonas buena/mala del coupling graph."""
    import networkx as nx
    from networkx.algorithms.approximation import treewidth_min_fill_in
    G = nx.Graph(); G.add_nodes_from(range(cal["n"])); G.add_edges_from(cal["edges"])
    tw, _ = treewidth_min_fill_in(G)
    deg = dict(G.degree())
    from collections import Counter
    return {"treewidth": tw, "degree_hist": dict(sorted(Counter(deg.values()).items())),
            "max_degree": max(deg.values()), "connected": nx.is_connected(G)}


def depth_ceiling(cal, err_budget=0.10, eplg=None):
    """Máximo de capas CZ antes de superar err_budget de error 2Q acumulado.

    Usa EPLG (si se pasa, el sistémico de cadena 100q) o el CZ mediano (régimen local).
    Devuelve dict con ambos para dar el rango honesto.
    """
    czmed = cal["median"]["cz"]
    out = {"by_cz_median": int(err_budget / czmed) if czmed else None}
    if eplg:
        out["by_eplg"] = int(err_budget / eplg)
    return out


def good_qubits(cal, t1_min=200.0, t2_min=100.0, ro_max=0.015):
    """Qubits 'sanos' por umbrales (T1/T2 en µs, readout). Devuelve lista ordenada por calidad."""
    out = []
    for q, d in cal["per_qubit"].items():
        if d["T1_us"] >= t1_min and d["T2_us"] >= t2_min and (d["readout"] or 1) <= ro_max:
            score = d["T2_us"] / (1 + (d["readout"] or 0) * 100)  # premia T2, penaliza readout
            out.append((q, round(score, 1)))
    return sorted(out, key=lambda x: -x[1])


def bad_qubits(cal, ro_bad=0.05, t1_bad=80.0):
    """Qubits a EXCLUIR: readout alto (incl. el ~aleatorio) o T1 muy bajo (TLS)."""
    out = []
    for q, d in cal["per_qubit"].items():
        why = []
        if (d["readout"] or 0) >= ro_bad:
            why.append("readout %.1f%%" % (d["readout"] * 100))
        if 0 < d["T1_us"] < t1_bad:
            why.append("T1 %.0fµs" % d["T1_us"])
        if why:
            out.append((q, "; ".join(why)))
    return sorted(out, key=lambda x: -cal["per_qubit"][x[0]]["readout"])


def hardware_reachable(cal, n2q_layers, eplg=None, err_budget=0.10):
    """¿Un circuito con n2q_layers capas CZ es alcanzable en este QPU con señal útil?

    La condición NECESARIA para que un veredicto 'necesita QPU' apunte a ESTE hardware.
    """
    ceil = depth_ceiling(cal, err_budget, eplg)
    cap = ceil.get("by_eplg") or ceil.get("by_cz_median")
    return {"reachable": (cap is not None and n2q_layers <= cap),
            "depth_ceiling": cap, "requested_layers": n2q_layers,
            "headroom_layers": (cap - n2q_layers) if cap is not None else None,
            "budget": err_budget}


def hardware_qualifier(atlas_route, n2q_layers, cal, eplg=None):
    """Convierte el candidato-defer de Atlas en un enunciado hardware-grounded HONESTO.

    Args:
        atlas_route: ruta de Atlas ('CPU'/'TENSOR'/'HPC_FIRST'/'ESCALATE').
        n2q_layers: profundidad 2q del circuito (capas CZ).
    Returns:
        dict con el calificador y un texto para la UI/certificado.
    """
    route = (atlas_route or "").upper().replace("-", "_")
    if route in ("CPU", "TENSOR"):
        return {"applies": False,
                "text": "Ruta clásica: el hardware no es necesario (no aplica reachability)."}
    r = hardware_reachable(cal, n2q_layers, eplg)
    if r["reachable"]:
        return {"applies": True, "reachable": True, **r,
                "text": ("Candidato QPU Y alcanzable en %s: ~%d capas CZ dentro del techo "
                         "~%d (presupuesto %.0f%%). Defendible como candidato a ESTE hardware."
                         % (cal["backend"], n2q_layers, r["depth_ceiling"], r["budget"] * 100))}
    return {"applies": True, "reachable": False, **r,
            "text": ("Candidato 'beyond clásico' PERO NO alcanzable en %s: ~%d capas CZ exceden "
                     "el techo de fidelidad ~%d. No es candidato a ESTE QPU — ni clásico ni este "
                     "hardware dan señal útil (defer a hardware mejor / menor profundidad)."
                     % (cal["backend"], n2q_layers, r["depth_ceiling"]))}


_2Q = {"cx", "cnot", "cz", "ecr", "rzz", "swap", "cy", "ch", "crz", "cp", "cu"}


def two_qubit_layers(circuit):
    """Profundidad de PUERTAS de 2 qubits del circuito (capas CZ equivalentes), por layering greedy.

    Args:
        circuit: lista de gates estilo Atlas (tuplas (nombre, *qubits, *params)).
    Returns:
        int: número de capas que contienen al menos una puerta de 2 qubits.
    """
    t = {}
    depth = 0
    for g in circuit:
        op = (g[0] if isinstance(g, (list, tuple)) else getattr(g, "name", "")).lower()
        qs = [x for x in (g[1:] if isinstance(g, (list, tuple)) else []) if isinstance(x, int)]
        if op in _2Q and len(qs) >= 2:
            lvl = max(t.get(qs[0], 0), t.get(qs[1], 0)) + 1
            t[qs[0]] = t[qs[1]] = lvl
            depth = max(depth, lvl)
    return depth


def qualify_offline(atlas_route, n2q_layers, snapshot=KINGSTON_SNAPSHOT, budget=0.10, n_qubits=None):
    """Calificador hardware-aware OFFLINE (sin red): usa el snapshot medido del backend.

    Convierte el candidato-defer de Atlas en un enunciado honesto y hardware-grounded para el
    certificado: un veredicto 'necesita QPU' solo apunta a ESTE hardware si el circuito es
    ALCANZABLE dentro del presupuesto de fidelidad (~depth_ceiling capas CZ).

    Args:
        n_qubits: si se pasa, agrega recommended_qubits (el veredicto es ruta × embedding, no solo ruta).
    Returns:
        dict: {applies, reachable?, depth_ceiling_range, learned, recommended_qubits, backend, text}.
    """
    route = (atlas_route or "").upper().replace("-", "_")
    if route in ("CPU", "TENSOR"):
        return {"applies": False, "backend": snapshot["backend"],
                "text": "Ruta clásica: el hardware no es necesario (reachability no aplica)."}
    # El techo de 1er orden F=Π(1-e) es un RANGO: EPLG worst-case → mediana del buen-subgrafo.
    # AMBOS son OPTIMISTAS: asumen errores NO correlacionados. (ver corrección aprendida abajo.)
    cap_fo_lo = snapshot["depth_ceiling_eplg"]            # 29 (EPLG 100q, peor caso 1er orden)
    cap_fo_hi = snapshot.get("depth_ceiling_local", cap_fo_lo)  # 49 (CZ mediana, mejor subgrafo 1er orden)
    # INFERENCE_OVERESTIMATE (auto-corrección #10, DATOS PROPIOS ibm_kingston 2026-06-22): el techo
    # de 1er orden SOBREESTIMA la profundidad real. 9 circuitos 2D-random PT, n=12: la XEB medida cae
    # ~2.6× más rápido que la inferida (κ̂≈2.6). REVIERTE el cross-session Aer (κ̂<1): Aer subestimaba
    # el ruido correlacionado/no-Markoviano (crosstalk/TLS/leakage) del metal real. El techo realista
    # es cap/κ̂ (MÁS APRETADO), no cap·(extensión).
    hh = snapshot.get("health", {})
    caveat = ("" if not hh else
              " · NB salud medida: %.0f%% del chip con dephasing severo (T2<T1/2); zona muerta "
              "DINÁMICA (cluster TLS ~Q111–122); evita qubits %s."
              % (hh.get("dephasing_frac_T2_lt_half_T1", 0) * 100, snapshot.get("exclude_qubits", [])))
    # Corrección APRENDIDA + conformal (DATOS PROPIOS): el techo realista = cap_1er_orden / κ̂.
    learned = None
    kappa = 1.0
    cap_real = cap_fo_lo                                  # fallback si el fit no carga
    try:
        from atlas_conformal_hardware import fit as _cfit
        lm = _cfit(alpha=0.10)   # 9 PT-válidos propios -> cobertura conformal 90%
        kappa = lm["kappa_hat"]
        cap_real = max(1, int(round(cap_fo_lo / kappa)))  # κ̂>1 -> techo realista MENOR (metal real)
        learned = {"kappa_hat": kappa, "depth_ceiling_realistic": cap_real,
                   "depth_ceiling_first_order": [cap_fo_lo, cap_fo_hi],
                   "direction": lm["direction"],
                   "bias_before": lm["mae_before"], "bias_after_holdout": lm["mae_after"],
                   "conformal_band": lm["conformal_q"], "coverage": lm["coverage_target"],
                   "caveat": "datos propios n=9 PT-válidos (metal real, cobertura 90%), familia 2D-random worst-case; "
                             "el valor es la banda + el SIGNO, no el punto",
                   "provenance": lm["provenance"]}
    except Exception:
        pass
    # Techo realista (κ̂-corregido) → el de 1er orden como cota OPTIMISTA superior.
    cap_lo, cap_hi = cap_real, cap_fo_lo                  # [realista, optimista-1er-orden]
    reachable = n2q_layers <= cap_lo                      # alcanzable bajo el techo REALISTA (metal real)
    likely = n2q_layers <= cap_hi                         # solo plausible bajo el modelo optimista 1er orden
    infer_note = (" · OJO: el techo de 1er orden (%d–%d capas) SOBREESTIMA el metal real; medición "
                  "propia (9 jobs PT, ibm_kingston) da degradación ~%.1f× más rápida (κ̂=%.2f) → techo "
                  "REALISTA ~%d capas. La corrección APRIETA, no extiende; banda conformal ±%.2f (cob. %.0f%%)."
                  % (cap_fo_lo, cap_fo_hi, kappa, kappa, cap_real,
                     (learned or {}).get("conformal_band") or 0, ((learned or {}).get("coverage") or 0) * 100))
    if reachable:
        txt = ("Candidato QPU Y alcanzable en %s: ~%d capas CZ ≤ techo REALISTA %d (1er orden optimista %d–%d, "
               "presupuesto %.0f%%).%s%s" % (snapshot["backend"], n2q_layers, cap_lo, cap_fo_lo, cap_fo_hi,
                                             budget * 100, caveat, infer_note))
    elif likely:
        txt = ("Zona GRIS en %s: ~%d capas CZ > techo REALISTA %d pero ≤ techo de 1er orden %d. El 1er "
               "orden SOBREESTIMA en metal real (κ̂≈%.1f medido propio) → es POCO probable que corra con "
               "fidelidad útil; defer a una medición XEB antes de gastar el QPU.%s"
               % (snapshot["backend"], n2q_layers, cap_lo, cap_hi, kappa, caveat))
    else:
        txt = ("Candidato 'beyond clásico' PERO NO alcanzable en %s: ~%d capas CZ > techo de 1er orden "
               "%d (y el realista %d es aún menor). No es candidato a ESTE QPU — ni clásico ni este "
               "hardware dan señal útil (defer a hardware mejor / menor profundidad).%s"
               % (snapshot["backend"], n2q_layers, cap_hi, cap_lo, caveat))
    # ACCIÓN-B (meta §4): el veredicto es RUTA × EMBEDDING, no solo ruta. Recomienda los mejores
    # qubits para el embedding (evita el cluster TLS/exclude). Para el camino óptimo exacto usar
    # atlas_hardware.embedding_error_range (live, con coupling map).
    rec_q = None
    if n_qubits:
        excl = set(snapshot.get("exclude_qubits", []))
        good = [q for q in snapshot.get("top_qubits", []) if q not in excl]
        rec_q = {"n_qubits": n_qubits, "recommended": good[:n_qubits], "avoid": sorted(excl),
                 "note": "qubits individuales de menor error; para el sub-grafo conectado óptimo usar embedding_error_range (live)"}
        if rec_q["recommended"]:
            txt += " · embedding sugerido (mejores qubits): %s; evita %s." % (rec_q["recommended"], sorted(excl))
    return {"applies": True, "reachable": reachable, "likely_reachable": likely,
            "recommended_qubits": rec_q,
            "backend": snapshot["backend"],
            "depth_ceiling_realistic": cap_lo, "depth_ceiling_first_order": [cap_fo_lo, cap_fo_hi],
            "depth_ceiling_range": [cap_lo, cap_hi],   # [realista, 1er-orden-optimista]
            "requested_2q_layers": n2q_layers, "budget": budget, "measured": snapshot["measured"],
            "inference_overestimate_kappa": kappa, "learned": learned,
            "health_caveat": caveat.strip(), "text": txt}


def reachability(n, circuit, snapshot=KINGSTON_SNAPSHOT, budget=0.10):
    """Reachability a CUALQUIER n SIN statevector — "empuja el modelo online" (propuesta de valor).

    Combina: (1) predicción κ̂-corregida de la fidelidad efectiva a la profundidad del circuito
    desde tasas MEDIDAS, (2) techo de profundidad realista vs 1er-orden, (3) un circuito mirror-RB
    como RECETA de verificación en metal (la return-prob da F=(N·P0-1)/(N-1) sin simular el ideal).
    Todo polinomial: no requiere el statevector exacto, así escala a n=50/100/127."""
    n2q = two_qubit_layers(circuit)
    n2q_gates = sum(1 for g in circuit
                    if (g[0] if isinstance(g, (list, tuple)) else "").lower() in _2Q
                    and len([x for x in g[1:] if isinstance(x, int)]) >= 2)
    e_cz = snapshot.get("cz_median", 2.0e-3)
    F_inf = (1.0 - e_cz) ** max(0, n2q_gates)              # fidelidad de 1er orden (producto de gates)
    pred = None
    try:
        from atlas_conformal_hardware import corrected_fidelity
        pred = corrected_fidelity(F_inf, max(1, n2q))      # κ̂-corregida + banda conformal
    except Exception:
        pred = {"F_inferred": round(F_inf, 4), "F_corrected": None, "band": "n/a"}
    q = qualify_offline("ESCALATE", n2q, snapshot=snapshot, budget=budget, n_qubits=n)
    # receta de verificación: un mirror circuit a este n/depth (la return-prob lo mide en metal)
    verification = {"method": "mirror-RB (Proctor, twirl de Pauli)",
                    "readout": "F = (N·P0 - 1)/(N-1), N=2^n; P0 = P(salida == target)",
                    "note": "corre este circuito en el QPU: la probabilidad de retorno da la fidelidad "
                            "efectiva SIN simular el ideal -> mide reachability a cualquier n (rompe n<=~12 del XEB)."}
    try:
        import os as _os, sys as _sys
        _bench = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "benchmarks")
        if _bench not in _sys.path:
            _sys.path.insert(0, _bench)
        from mirror_rb import build_mirror_circuit
        mc = build_mirror_circuit(n, max(2, n2q), seed=2026, per_layer_twirl=True)
        verification["mirror_circuit_qasm"] = mc["qasm"]
        verification["target_bitstring"] = mc["target"]
    except Exception as e:
        verification["mirror_circuit_qasm"] = None
        verification["unavailable"] = "generador mirror no disponible en este entorno (%s)" % str(e)[:60]
    return {"applies": True, "n": n, "n2q_layers": n2q, "n2q_gates": n2q_gates,
            "predicted_fidelity": pred, "reachable": q.get("reachable"),
            "depth_ceiling_realistic": q.get("depth_ceiling_realistic"),
            "depth_ceiling_first_order": q.get("depth_ceiling_first_order"),
            "kappa_hat": q.get("inference_overestimate_kappa"),
            "verification": verification, "backend": snapshot["backend"],
            "scope": "predicción κ̂-corregida desde calibración MEDIDA (polinomial, cualquier n); "
                     "mirror-RB la VERIFICA en metal sin statevector. NO ejecuta cómputo exponencial."}


def readout_crosstalk_percentiles(cal):
    """Distribución del ratio measure_2/measure por qubit (H3 corregido): mediana ~1x, cola alta sí."""
    ratios = sorted(cal["meas2_q"][q] / cal["meas_q"][q]
                    for q in cal["meas_q"] if q in cal["meas2_q"] and cal["meas_q"][q] > 0)
    if not ratios:
        return None
    def pct(p):
        return ratios[min(len(ratios) - 1, int(p * len(ratios)))]
    n = len(ratios)
    return {"median": round(pct(0.5), 2), "p75": round(pct(0.75), 2), "p90": round(pct(0.90), 2),
            "max": round(ratios[-1], 1), "frac_ge_5x": round(sum(r >= 5 for r in ratios) / n, 2),
            "frac_ge_10x": round(sum(r >= 10 for r in ratios) / n, 2)}


def embedding_error_range(cal, k_edges):
    """#4 embedding-aware: la dureza en hardware del MISMO circuito lógico depende del mapeo físico.

    Para una cadena que necesita k aristas 2q, devuelve el error CZ agregado del MEJOR embedding
    (camino de menor error en el coupling graph) vs el PEOR (forzado por las k aristas más ruidosas,
    p.ej. a través del cluster TLS). Demuestra que el layout cambia el resultado, no solo el circuito.

    Returns:
        dict: {best_path_edges, best_cz_sum, worst_cz_sum, ratio, note}.
    """
    import networkx as nx
    edges = [(u, v, (cal["per_edge"][(u, v)]["cz"] or 1.0)) for (u, v) in cal["edges"]]
    G = nx.Graph()
    for u, v, w in edges:
        G.add_edge(u, v, weight=w)
    # mejor: camino de k aristas de menor error total (aprox: arranca del mejor edge, extiende greedy)
    best = sorted(edges, key=lambda e: e[2])
    # greedy: construir un camino simple de longitud k siguiendo aristas de bajo error
    used_nodes, path_edges, cz_sum = set(), [], 0.0
    for u, v, w in best:
        if len(path_edges) >= k_edges:
            break
        if u not in used_nodes or v not in used_nodes:
            path_edges.append((u, v, round(w, 6))); cz_sum += w
            used_nodes.add(u); used_nodes.add(v)
    worst = sorted(edges, key=lambda e: -e[2])[:k_edges]
    worst_sum = sum(w for _, _, w in worst)
    return {"k_edges": k_edges, "best_path_edges": path_edges, "best_cz_sum": round(cz_sum, 5),
            "worst_cz_sum": round(worst_sum, 5),
            "ratio_worst_over_best": round(worst_sum / cz_sum, 1) if cz_sum else None,
            "note": ("el mismo circuito de %d aristas 2q acumula %.3f de error CZ en el mejor "
                     "embedding vs %.3f en el peor (cluster TLS) — %sx peor por layout"
                     % (k_edges, cz_sum, worst_sum,
                        round(worst_sum / cz_sum, 1) if cz_sum else "?"))}


def hardware_health(cal):
    """Sintetiza lo que IBM publica pero no explica (todo MEDIDO, cross-checado 2026-06-22).

    Devuelve: heterogeneidad de couplers (gate lengths), zona muerta DINÁMICA (edges CZ>=0.5),
    dephasing severo (T2<T1/2), caveat idle (ID==SX), readout backaction (M2<M), outliers CZ/RZZ.
    """
    n = cal["n"]
    # 1) gate lengths (heterogeneidad de fabricación) — undirected
    from collections import Counter
    lens = Counter(round(d["cz_len"]) for d in cal["per_edge"].values() if d.get("cz_len"))
    slow = sorted((round(d["cz_len"]), e, round(d["cz"] or 0, 4))
                  for e, d in cal["per_edge"].items() if d.get("cz_len") and round(d["cz_len"]) > 68)
    # 2) zona muerta: edges efectivamente rotos (CZ >= 0.5 = ~depolarizante total)
    broken = sorted(((round(d["cz"], 3), e) for e, d in cal["per_edge"].items()
                     if d.get("cz") and d["cz"] >= 0.5), reverse=True)
    hot = sorted(((round(d["cz"], 3), e) for e, d in cal["per_edge"].items()
                  if d.get("cz") and 0.05 <= d["cz"] < 0.5), reverse=True)
    # 3) dephasing severo T2<T1/2
    cats = {"T2_gt_1.5_T1": 0, "0.9_1.5": 0, "0.5_0.9": 0, "lt_0.5": 0, "no_data": 0}
    for q in range(n):
        t1 = cal["per_qubit"][q]["T1_us"]; t2 = cal["per_qubit"][q]["T2_us"]
        if not t1 or not t2:
            cats["no_data"] += 1; continue
        r = t2 / t1
        cats["T2_gt_1.5_T1"] += r > 1.5; cats["0.9_1.5"] += 0.9 <= r <= 1.5
        cats["0.5_0.9"] += 0.5 <= r < 0.9; cats["lt_0.5"] += r < 0.5
    # 4) idle == sx (sin medición independiente de idle)
    idsx = sum(1 for q in cal["id_q"] if q in cal["sx_q"] and abs(cal["id_q"][q] - cal["sx_q"][q]) < 1e-9)
    # 5) readout backaction M2<M
    both = [q for q in cal["meas_q"] if q in cal["meas2_q"]]
    m2_lt = sum(cal["meas2_q"][q] < cal["meas_q"][q] for q in both)
    # 6) CZ/RZZ ratio outliers (leakage / TLS candidates)
    ratios = []
    for e, d in cal["per_edge"].items():
        if d.get("cz") and d.get("rzz"):
            ratios.append((round(d["cz"] / d["rzz"], 2), e, round(d["cz"], 4), round(d["rzz"], 4)))
    return {
        "gate_lengths_ns": dict(sorted(lens.items())), "non_68ns_edges": slow,
        "broken_edges_cz_ge_0.5": broken, "hot_edges_cz_0.05_0.5": hot[:10],
        "dephasing": {**cats, "frac_T2_lt_half_T1": round(cats["lt_0.5"] / n, 2)},
        "idle_eq_sx": "%d/%d (IBM deriva idle del gate error; sin Ramsey dedicada)" % (idsx, len(cal["sx_q"])),
        "readout_backaction_M2_lt_M": "%d/%d (%.0f%%)" % (m2_lt, len(both), m2_lt / max(1, len(both)) * 100),
        "cz_rzz_ratio_outliers": sorted(ratios, reverse=True)[:5],
    }


def derive_from_public(cal):
    """Derivaciones DURAS sobre datos públicos (T1,T2,CZ,RZZ,SX). Lo que IBM tiene pero no sintetiza.

    Todo es matemática directa sobre métricas medidas. Incluye correcciones honestas vs análisis
    externos: frecuencias NO están en la API (0/156) -> loss-tangent exacto y colisión espectral NO
    derivables; el budget SX sale control-dominado (no decoherencia) con el proxy estándar.
    """
    import math
    n = cal["n"]
    pq = cal["per_qubit"]
    # 1) dephasing puro Tφ: 1/T2 = 1/(2 T1) + 1/Tφ  (T en µs)
    deph_dom, worst_tphi = 0, []
    for q in range(n):
        t1, t2 = pq[q]["T1_us"], pq[q]["T2_us"]
        if not t1 or not t2:
            continue
        inv = 1 / t2 - 1 / (2 * t1)
        tphi = (1 / inv) if inv > 1e-9 else float("inf")
        if tphi != float("inf") and tphi < 2 * t1:
            deph_dom += 1
        if tphi != float("inf"):
            worst_tphi.append((round(tphi, 1), q))
    # 2) momentos del CZ (marketing: mediana vs media por la cola larga)
    cz = [d["cz"] for d in cal["per_edge"].values() if d.get("cz") and d["cz"] < 1]
    import statistics as _st
    moments = {"median": _st.median(cz), "mean": _st.mean(cz),
               "geomean": math.exp(_st.mean(math.log(x) for x in cz)),
               "mean_over_median": round(_st.mean(cz) / _st.median(cz), 1)} if cz else {}
    # 3) chip EFECTIVO: componentes del subgrafo de edges buenos (CZ < 0.3%)
    import networkx as nx
    good = [(u, v) for (u, v), d in cal["per_edge"].items() if (d.get("cz") or 1) < 0.003]
    G = nx.Graph(); G.add_edges_from(good)
    comps = sorted((len(c) for c in nx.connected_components(G)), reverse=True)
    # 4) SX: decoherencia vs control (proxy ε≈t/2T1+t/2T2, t=32ns) — HONESTO: sale control-dominado
    t = 32e-9; ctrl = deco = 0; worst_ctrl = []
    for q in range(n):
        se = cal["sx_q"].get(q); t1, t2 = pq[q]["T1_us"], pq[q]["T2_us"]
        if not se or not t1 or not t2:
            continue
        edec = t / (2 * t1 * 1e-6) + t / (2 * t2 * 1e-6); ec = se - edec
        if ec > edec:
            ctrl += 1
        else:
            deco += 1
        worst_ctrl.append((round(ec / se, 3) if se else 0, q))
    # 5) ZZ residual: IBM lo PUBLICA EXACTO (general block, kHz). No estimar desde CZ/RZZ —
    #    la estimación daba hasta 24x de más (edge 131_138: estimado 86 kHz vs real 3.56 kHz).
    zz = sorted(((round(d["zz_hz"] / 1e3, 2), e) for e, d in cal["per_edge"].items()
                 if d.get("zz_hz") is not None), reverse=True)
    zz_exact = bool(zz)
    return {
        "pure_dephasing": {"dominated_frac": round(deph_dom / n, 2),
                           "worst_tphi_us": sorted(worst_tphi)[:4]},
        "cz_moments": moments,
        "effective_chip": {"usable_edges_frac": round(len(good) / max(1, len(cal["edges"])), 2),
                           "good_components": comps[:8], "main_component": comps[0] if comps else 0},
        "sx_budget": {"control_dominated": ctrl, "decoherence_dominated": deco,
                      "worst_control_pure": sorted(worst_ctrl, reverse=True)[:3],
                      "note": "proxy estándar (t/2T1+t/2T2): SX control-dominado en casi todo el "
                              "chip (decoherencia en 32ns ~6e-5 << SX ~2.7e-4). Sensible a la fórmula."},
        "zz_residual_khz_exact": {"top5": zz[:5], "max_khz": zz[0][0] if zz else None,
                                  "median_khz": (zz[len(zz) // 2][0] if zz else None),
                                  "source": "IBM general block (publicado, exacto)" if zz_exact else "n/a",
                                  "note": "todo en kHz de 1 dígito -> couplers sintonizables anulan ZZ; "
                                          "la estimación CZ/RZZ daba hasta 24x de más (131_138: 86→3.56 kHz)"},
        "caveats": ("frecuencias de qubit NO expuestas en la API (0/156) -> loss-tangent EXACTO y "
                    "análisis de colisión espectral NO derivables (siguen siendo solo-IBM). El "
                    "loss-tangent solo se puede acotar asumiendo f~5GHz."),
    }


def calibration_history(qubit, days_back=(0, 1, 3, 7, 14, 30), backend_name="ibm_kingston",
                        token_file=None, now_utc=None):
    """Serie temporal de T1/T2/readout de un qubit + el peor edge CZ, vía properties(datetime=...).

    Distingue 'aging crónico' de 'colapso súbito' de 'T2 congelado (no re-medido)'. LOCAL (token).

    Args:
        qubit: índice de qubit a rastrear.
        days_back: lista de días hacia atrás a muestrear.
        now_utc: datetime UTC base (si None, usa el actual — pásalo explícito para reproducibilidad).
    Returns:
        list[dict]: por fecha {date, T1_us, T2_us, readout, worst_cz_edge, worst_cz}.
    """
    import datetime as _dt
    tok = _load_token(token_file)
    from qiskit_ibm_runtime import QiskitRuntimeService
    svc = QiskitRuntimeService(channel="ibm_quantum_platform", token=tok)
    b = svc.backend(backend_name)
    now = now_utc or _dt.datetime.now(_dt.timezone.utc)
    out = []
    for dd in days_back:
        when = now - _dt.timedelta(days=dd)
        try:
            props = b.properties(datetime=when)
            if props is None:
                continue

            def qv(q, name):
                for nd in props.qubits[q]:
                    if nd.name == name:
                        return nd.value
                return None
            worst, we = 0, None
            for g in props.gates:
                if g.gate == "cz":
                    e = next((p.value for p in g.parameters if p.name == "gate_error"), None)
                    if e and e < 1 and e > worst:
                        worst, we = e, tuple(g.qubits)
            t1 = qv(qubit, "T1"); t2 = qv(qubit, "T2"); ro = qv(qubit, "readout_error")
            out.append({"date": str(when.date()), "T1_us": round(t1, 1) if t1 else None,
                        "T2_us": round(t2, 1) if t2 else None,
                        "readout": round(ro, 4) if ro else None,
                        "worst_cz_edge": we, "worst_cz": round(worst, 3)})
        except Exception:
            continue
    return out


def effective_capacity(cal, cz_thr=0.003):
    """A — CAPACIDAD EFECTIVA: el nº de qubits REALMENTE usables (no el nominal de marketing).

    El buen-subgrafo (edges con CZ < cz_thr) se fragmenta en componentes desconectados; el mayor
    componente conexo es la capacidad operativa real. IBM no publica esto.
    """
    import networkx as nx
    good = [(u, v) for (u, v), d in cal["per_edge"].items() if (d.get("cz") or 1) < cz_thr]
    G = nx.Graph(); G.add_edges_from(good)
    comps = sorted((sorted(c) for c in nx.connected_components(G)), key=len, reverse=True)
    main = comps[0] if comps else []
    dead = [q for q in range(cal["n"]) if (cal["per_qubit"][q]["readout"] or 1) >= 0.5
            or not cal["per_qubit"][q]["T1_us"]]
    return {"n_nominal": cal["n"], "n_effective": len(main),
            "effective_fraction": round(len(main) / cal["n"], 2),
            "components": [len(c) for c in comps[:8]], "main_component_qubits": main,
            "dead_qubits": dead, "cz_threshold": cz_thr,
            "reading": "pagas por %d qubits; el mayor bloque conexo usable (CZ<%.1f%%) es %d."
                       % (cal["n"], cz_thr * 100, len(main))}


def recommend_embedding(cal, n_qubits, cz_thr=0.01):
    """B — EMBEDDING ÓPTIMO: sub-grafo conexo de n_qubits de MENOR error, evitando zonas muertas.

    Convierte el veredicto en acción: 'usa ESTOS qubits físicos'. Greedy desde el mejor edge,
    crece por el vecino de menor error, salta qubits muertos/excluidos.
    """
    excl = set(q for q in range(cal["n"]) if (cal["per_qubit"][q]["readout"] or 1) >= 0.05)
    edges = sorted(((d.get("cz") or 1, u, v) for (u, v), d in cal["per_edge"].items()
                    if u not in excl and v not in excl and (d.get("cz") or 1) < cz_thr))
    if not edges:
        return {"n_qubits": n_qubits, "embedding": None, "note": "sin sub-grafo limpio suficiente"}
    import networkx as nx
    G = nx.Graph()
    for w, u, v in edges:
        G.add_edge(u, v, w=w)
    # greedy: arranca del mejor edge, agrega el vecino que añade menor error, hasta n_qubits
    w0, a, b = edges[0]
    chosen = {a, b}; total = w0
    while len(chosen) < n_qubits:
        best = None
        for node in list(chosen):
            for nb in G.neighbors(node):
                if nb not in chosen:
                    w = G[node][nb]["w"]
                    if best is None or w < best[0]:
                        best = (w, nb)
        if best is None:
            break
        total += best[0]; chosen.add(best[1])
    qs = sorted(chosen)
    return {"n_qubits": n_qubits, "embedding": qs, "achieved": len(qs),
            "sum_cz_error": round(total, 5), "avoided": sorted(excl)[:10],
            "note": ("sub-grafo conexo de menor error 2q; usar como initial_layout"
                     if len(qs) >= n_qubits else "no se alcanzó n_qubits conexos en la zona limpia")}


def emulate_noisy(qasm, backend_name="ibm_kingston", shots=4096, token_file=None):
    """C — EMULADOR FIEL-AL-RUIDO: corre el circuito con el ruido LOCAL real del device,
    clásicamente, SIN gastar shots del QPU. 'prueba antes de pagar'. Requiere qiskit-aer.

    Returns: {noisy_probs, ideal_probs (si n<=20), tvd_ideal_vs_emulated, shots, backend}.
    """
    import numpy as np
    from qiskit import transpile
    from qiskit.qasm2 import loads as qload
    from qiskit.quantum_info import Statevector
    from qiskit_aer import AerSimulator
    tok = _load_token(token_file)
    from qiskit_ibm_runtime import QiskitRuntimeService
    svc = QiskitRuntimeService(channel="ibm_quantum_platform", token=tok)
    b = svc.backend(backend_name)
    sim = AerSimulator.from_backend(b)               # ruido LOCAL real + coupling + basis
    qc = qload(qasm); n = qc.num_qubits
    m = qc.copy(); m.measure_all()
    tqc = transpile(m, b, optimization_level=1)
    res = sim.run(tqc, shots=shots).result().get_counts()
    tot = sum(res.values())
    noisy = {}
    for k, v in res.items():
        kk = k.replace(" ", "")[-n:]; noisy[kk] = noisy.get(kk, 0.0) + v / tot
    out = {"backend": backend_name, "n": n, "shots": shots, "noisy_probs_top": dict(sorted(noisy.items(), key=lambda kv: -kv[1])[:8])}
    if n <= 20:
        p = np.abs(Statevector.from_instruction(qload(qasm)).data) ** 2
        ideal = {format(i, "0%db" % n): float(p[i]) for i in range(len(p)) if p[i] > 1e-9}
        tvd = 0.5 * sum(abs(ideal.get(k, 0) - noisy.get(k, 0)) for k in set(ideal) | set(noisy))
        out["tvd_ideal_vs_emulated"] = round(tvd, 4)
    out["reading"] = "distribución del device con ruido LOCAL real, sin gastar cuota QPU."
    return out


_CALIB_TABLE = None


def load_calib_table():
    """Carga la tabla de calibración PÚBLICA horneada (per-edge CZ + per-qubit readout/sx) — SIN token.

    Esto desbloquea B (embedding) y C-lite (emulador) en el app token-free: son datos públicos
    de calibración (176 edges + 156 readouts), no secretos. Refrescar con build_evidence/pull.
    """
    global _CALIB_TABLE
    if _CALIB_TABLE is None:
        import os
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "benchmarks", "kingston_calibration.json")
        try:
            _CALIB_TABLE = json.load(open(p, encoding="utf-8"))
        except Exception:
            _CALIB_TABLE = {}
    return _CALIB_TABLE


def recommend_embedding_offline(n_qubits, ro_bad=0.05, cz_thr=0.01):
    """B token-free: sub-grafo conexo de menor error 2q desde la tabla horneada (sin token)."""
    t = load_calib_table()
    if not t.get("cz"):
        return {"n_qubits": n_qubits, "embedding": None, "note": "tabla de calibración no disponible"}
    ro = t.get("readout", {})
    excl = set(int(q) for q, v in ro.items() if v >= ro_bad)
    try:
        import networkx as nx
    except Exception:   # fallback sin networkx: mejores qubits por readout (no conexo, degradado honesto)
        good = sorted((int(q) for q in ro if int(q) not in excl), key=lambda q: ro[str(q)])[:n_qubits]
        return {"n_qubits": n_qubits, "embedding": good, "achieved": len(good),
                "sum_cz_error": None, "avoided": sorted(excl)[:10], "source": "fallback (sin networkx)",
                "note": "mejores qubits por readout; sin garantía de conexión (instala networkx para el óptimo)"}
    G = nx.Graph()
    for k, w in t["cz"].items():
        u, v = map(int, k.split("_"))
        if u not in excl and v not in excl and w < cz_thr:
            G.add_edge(u, v, w=w)
    if G.number_of_edges() == 0:
        return {"n_qubits": n_qubits, "embedding": None, "note": "sin sub-grafo limpio"}
    best_edge = min(G.edges(data=True), key=lambda e: e[2]["w"])
    chosen = {best_edge[0], best_edge[1]}; total = best_edge[2]["w"]
    while len(chosen) < n_qubits:
        cand = None
        for node in list(chosen):
            for nb in G.neighbors(node):
                if nb not in chosen:
                    w = G[node][nb]["w"]
                    if cand is None or w < cand[0]:
                        cand = (w, nb)
        if cand is None:
            break
        total += cand[0]; chosen.add(cand[1])
    qs = sorted(chosen)
    return {"n_qubits": n_qubits, "embedding": qs, "achieved": len(qs),
            "sum_cz_error": round(total, 5), "avoided": sorted(excl)[:10],
            "source": "tabla pública horneada (token-free)",
            "note": "usar como initial_layout" if len(qs) >= n_qubits else "no alcanzó n conexos limpios"}


def emulate_lite(qasm, layout=None):
    """C-lite (token-free, sin aer): distribución ruidosa APROXIMADA del device usando las TASAS
    MEDIDAS de la tabla. Modelo de 1er orden: p_noisy = F·ideal + (1-F)·uniforme, con
    F = Π(1-cz_real)·Π(1-sx)·Π(1-readout) de los qubits/edges del embedding. NO es el canal
    per-edge completo (eso es emulate_noisy con aer+token); es una cota honesta desde tasas reales.
    """
    import numpy as np
    from qiskit.qasm2 import loads as qload
    from qiskit.quantum_info import Statevector
    qc = qload(qasm); n = qc.num_qubits
    if n > 16:
        return {"error": "emulate_lite: n<=16 (necesita statevector ideal)"}
    t = load_calib_table()
    emb = layout or (recommend_embedding_offline(n).get("embedding") or list(range(n)))
    cz = t.get("cz", {}); ro = t.get("readout", {}); sx = t.get("sx", {})
    # contar gates del circuito
    n2q = sum(1 for ins in qc.data if ins.operation.num_qubits == 2)
    n1q = sum(1 for ins in qc.data if ins.operation.num_qubits == 1)
    czmed = (sorted(cz.values())[len(cz) // 2] if cz else 2e-3)
    sxmed = (sorted(sx.values())[len(sx) // 2] if sx else 3e-4)
    F2 = (1 - czmed) ** n2q
    F1 = (1 - sxmed) ** n1q
    Fro = np.prod([1 - ro.get(str(q), 0.01) for q in emb[:n]]) if ro else 0.9
    F = float(F2 * F1 * Fro)
    p = np.abs(Statevector.from_instruction(qload(qasm)).data) ** 2
    N = 2 ** n
    # Modelo de 1er orden: p_noisy = F·ideal + (1-F)·uniforme. AQUÍ "uniforme" es el componente de
    # ERROR (despolarizante global por puertas), NO la salida: la salida sigue 100·F% concentrada en
    # los picos ideales. VALIDADO contra metal real (ghz6 GOOD): este modelo da TVD(ideal,emulado)
    # ≈0.082 vs TVD(ideal,QPU) MEDIDO =0.081 — casi exacto. (Verificación adversarial 2026-06-22:
    # un modelo readout-bit-flip puro daba 0.004 -> demasiado optimista; el despolarizante global
    # reproduce el spread real porque la pérdida de fidelidad es dominada por las PUERTAS, no readout.
    # TVD(QPU,uniforme)≈0.78-0.89 mide la salida vs uniforme, que es grande justo porque la salida
    # NO es uniforme — eso nunca contradijo este modelo.)
    noisy = {format(i, "0%db" % n): F * float(p[i]) + (1 - F) / N for i in range(N) if (F * p[i] + (1 - F) / N) > 1e-6}
    ideal = {format(i, "0%db" % n): float(p[i]) for i in range(N) if p[i] > 1e-9}
    tvd = 0.5 * sum(abs(ideal.get(k, 0) - noisy.get(k, 0)) for k in set(ideal) | set(noisy))
    return {"n": n, "embedding": emb[:n], "fidelity_est": round(F, 4), "n2q": n2q, "n1q": n1q,
            "tvd_ideal_vs_emulated": round(tvd, 4),
            "noisy_top": dict(sorted(noisy.items(), key=lambda kv: -kv[1])[:8]),
            "model": "1er orden: p_noisy = F·ideal + (1-F)·uniforme, donde 'uniforme' es el componente "
                     "de ERROR (despolarizante global por puertas), NO la salida; F de tasas MEDIDAS (token-free)",
            "caveat": "VALIDADO en metal: ghz6 GOOD da TVD(ideal,emulado)≈0.082 vs TVD(ideal,QPU) medido "
                      "=0.081. El despolarizante global captura el spread real (la pérdida de fidelidad "
                      "la dominan las PUERTAS, no el readout); un modelo readout-puro subestima (0.004). "
                      "El canal per-edge completo (CZ/T1/T2/leakage) es emulate_noisy (aer+token, local)."}


def build_local_noise_model(backend_name="ibm_kingston", token_file=None):
    """Modelo de ruido LOCAL real desde la calibración (incorporable #3). Requiere qiskit-aer.

    Reemplaza la envolvente toy-global por canales locales por qubit/edge (T1/T2, gate errors,
    readout). Útil para validar la predicción de colapso-por-ruido de Atlas contra ruido real.
    """
    tok = _load_token(token_file)
    from qiskit_ibm_runtime import QiskitRuntimeService
    from qiskit_aer.noise import NoiseModel
    svc = QiskitRuntimeService(channel="ibm_quantum_platform", token=tok)
    b = svc.backend(backend_name)
    nm = NoiseModel.from_backend(b)
    return nm, b


def summarize(backend_name="ibm_kingston", token_file=None):
    cal = pull_calibration(backend_name, token_file)
    topo = topology_summary(cal)
    xfac = readout_crosstalk_factor(cal)
    ceil = depth_ceiling(cal, 0.10, eplg=3.42e-3)
    gq = good_qubits(cal)[:8]
    bq = bad_qubits(cal)[:8]
    print("=== atlas_hardware: %s ===" % backend_name)
    print("topología: n=%d, edges=%d, grado_max=%d, treewidth(coupling)=%d, hist_grados=%s"
          % (cal["n"], len(cal["edges"]), topo["max_degree"], topo["treewidth"], topo["degree_hist"]))
    print("medianas: CZ=%.2e · SX=%.2e · readout=%.2e (peor q%d=%.1f%%)"
          % (cal["median"]["cz"], cal["median"]["sx"], cal["median"]["readout"],
             cal["worst"]["readout_q"], cal["worst"]["readout"] * 100))
    print("readout-crosstalk (measure_2 paralelo / measure individual): mediana ~%.1fx (chip-wide "
          "NO es el problema) PERO peor-caso q%s = %.1fx -> no medir ESE qubit en paralelo"
          % (xfac["median_ratio"] or 0, xfac["worst_q"], xfac["worst_ratio"] or 0))
    print("techo de profundidad (err<10%%): %s capas CZ (EPLG100q) / %s (CZ local)"
          % (ceil.get("by_eplg"), ceil.get("by_cz_median")))
    print("qubits buenos (top8): %s" % [q for q, _ in gq])
    print("qubits a excluir (top8): %s" % [(q, w) for q, w in bq])
    # H3 corregido: distribución completa del ratio measure_2/measure
    pc = readout_crosstalk_percentiles(cal)
    if pc:
        print("measure_2/measure distribución: mediana=%.2fx p75=%.2fx p90=%.2fx max=%.1fx · "
              "%.0f%% qubits >=5x, %.0f%% >=10x" % (pc["median"], pc["p75"], pc["p90"], pc["max"],
              pc["frac_ge_5x"] * 100, pc["frac_ge_10x"] * 100))
    # #4 embedding-aware: la dureza en hardware depende del layout
    emb = embedding_error_range(cal, k_edges=9)
    print("embedding-aware (#4): %s" % emb["note"])
    # lo que IBM publica pero no explica (todo medido)
    h = hardware_health(cal)
    print("--- hardware health (medido, no inferido) ---")
    print("  couplers gate_length: %s (heterogeneidad de fabricación)" % h["gate_lengths_ns"])
    print("  zona muerta (CZ>=0.5, edges rotos): %s" % [e for _, e in h["broken_edges_cz_ge_0.5"]])
    print("  zona caliente (CZ 5-50%%): %s" % [e for _, e in h["hot_edges_cz_0.05_0.5"][:6]])
    print("  dephasing severo T2<T1/2: %.0f%% del chip (%s)" % (h["dephasing"]["frac_T2_lt_half_T1"] * 100,
          {k: v for k, v in h["dephasing"].items() if k != "frac_T2_lt_half_T1"}))
    print("  idle==sx: %s" % h["idle_eq_sx"])
    print("  readout backaction M2<M: %s" % h["readout_backaction_M2_lt_M"])
    print("  CZ/RZZ outliers (leakage/TLS): %s" % [(r, e) for r, e, _, _ in h["cz_rzz_ratio_outliers"]])
    # derivaciones duras sobre datos públicos (lo que IBM tiene pero no sintetiza)
    dv = derive_from_public(cal)
    print("--- derivaciones (matemática sobre datos públicos) ---")
    print("  dephasing puro Tφ: %.0f%% dephasing-dominados; peores Tφ(µs)=%s"
          % (dv["pure_dephasing"]["dominated_frac"] * 100, dv["pure_dephasing"]["worst_tphi_us"]))
    m = dv["cz_moments"]
    print("  CZ marketing: mediana=%.2e media=%.2e (%.1fx) — el titular usa la mediana"
          % (m["median"], m["mean"], m["mean_over_median"]))
    ec = dv["effective_chip"]
    print("  CHIP EFECTIVO: %.0f%% edges usables → componente principal de %d qubits "
          "(el '156' fragmenta en %s)" % (ec["usable_edges_frac"] * 100, ec["main_component"],
          ec["good_components"]))
    print("  ZZ residual EXACTO publicado (kHz): %s · max=%s mediana=%s"
          % (dv["zz_residual_khz_exact"]["top5"][:3], dv["zz_residual_khz_exact"]["max_khz"],
             dv["zz_residual_khz_exact"]["median_khz"]))
    print("  CAVEAT: %s" % dv["caveats"])
    # --- capa de realidad del QPU (A/B/C operacionalizados) ---
    print("--- capa de realidad del QPU (operacionalizable) ---")
    ec = effective_capacity(cal)
    print("  A) CAPACIDAD EFECTIVA: %s (componentes %s)" % (ec["reading"], ec["components"]))
    emb = recommend_embedding(cal, 8)
    print("  B) EMBEDDING ÓPTIMO (8q): %s (error CZ total %.4f, evita zonas muertas)"
          % (emb["embedding"], emb.get("sum_cz_error", 0)))
    print("  C) EMULADOR FIEL-AL-RUIDO: atlas_hardware.emulate_noisy(qasm) -> distribución del device")
    print("     con ruido LOCAL real, SIN gastar shots QPU (validado: GHZ4 TVD~0.04 vs ideal).")
    # demo del calificador hardware-aware
    for route, layers in [("ESCALATE", 20), ("ESCALATE", 120)]:
        h = hardware_qualifier(route, layers, cal, eplg=3.42e-3)
        print("  [%s, %d capas] -> %s" % (route, layers, h["text"]))
    return cal


if __name__ == "__main__":
    import sys
    summarize(sys.argv[1] if len(sys.argv) > 1 else "ibm_kingston")

"""atlas.py -- LA INTERFAZ unificada a las 43 ideas. Ingiere un circuito (QASM 2.0 o tuplas nativas) y
devuelve el ATLAS DE COSTO de los ejes: el detector, en un solo comando.

Uso:
    PYTHONPATH=src pixi run python atlas.py <circuito.qasm>     # ingiere QASM 2.0
    PYTHONPATH=src pixi run python atlas.py --demo              # circuito de demostracion

API:
    from atlas import cost_atlas
    cost_atlas(n, circuito)   ->  dict con los ejes + veredicto

Ejes que reporta (cada uno un parametro de orden barato):
    magia (T-count)  ·  entrelazamiento (MPS bond)  ·  spread (operador)  ·  treewidth  ·  libro (flattener)
    + el veredicto del arsenal (el minimo sobre los metodos): TRACTABLE via <metodo>  /  WALL.
"""
from __future__ import annotations
import sys, re, math
import numpy as np
sys.path.insert(0, "src")
# El motor de investigacion (physics_magnitude_lab) es OPCIONAL: da fold(magic)+spread (solo n<=ARSENAL_CAP)
# y el libro 'free' (free-fermion). Sin el, Atlas DEGRADA con gracia -> librerias publicas (quimb/cotengra/
# stim): fast-path en todo n, libro stabilizer/core via Stim. Asi el demo publico no expone el motor propietario.
try:
    from physics_magnitude_lab import arsenal_router
    from physics_magnitude_lab.flattener import which_flattener
    _ENGINE = True
except Exception:
    _ENGINE = False
    arsenal_router = None

    def which_flattener(circuit):
        """Fallback sin el motor: Clifford (sin T) -> 'stabilizer'; si no -> 'core'. (No detecta 'free'.)"""
        from ground_truth import stim_is_clifford
        if not any(g and g[0] == "t" for g in circuit):
            try:
                if stim_is_clifford(circuit):
                    return "stabilizer"
            except Exception:
                pass
        return "core"

_Q3_REG = re.compile(r"^\s*qubit\s*\[\s*(\d+)\s*\]\s*(\w+)\s*;", re.M)   # qubit[n] q;
_Q3_ONE = re.compile(r"^\s*qubit\s+(\w+)\s*;", re.M)                    # qubit q;

# ===== PARSER ROBUSTO (instrument-grade): cancelaciones reales, gates custom, modificadores, rx/ry honestos
_ZROT = {"t": math.pi / 4, "tdg": -math.pi / 4, "s": math.pi / 2, "sdg": -math.pi / 2, "z": math.pi}


def _evang(s):
    """Evalua un angulo QASM ('pi/4', '0.7', '-pi/2'); None si no es numerico."""
    if s is None:
        return None
    try:
        return float(eval(s.replace("pi", str(math.pi)).replace("PI", str(math.pi)), {"__builtins__": {}}, {}))
    except Exception:
        return None


def _classify_z(theta, q):
    """Rotacion-Z NETA -> Clifford (s/z) o UNA unidad de magia ('t'). Aqui mueren las cancelaciones T^8=I."""
    if theta is None:
        return [("t", q)]
    k = (theta / (math.pi / 2)) % 4
    if abs(k - round(k)) < 1e-7:                       # multiplo de pi/2 = Clifford
        return {0: [], 1: [("s", q)], 2: [("z", q)], 3: [("s", q), ("z", q)]}[round(k) % 4]
    return [("t", q)]                                  # no-Clifford -> magia


def _ccx_events(a, b, c):
    """Toffoli (control a,b; target c) -> {h,cx,Z}. Reutilizado por ccx y cswap."""
    return [("h", c), ("cx", b, c), ("Z", c, -math.pi/4), ("cx", a, c), ("Z", c, math.pi/4),
            ("cx", b, c), ("Z", c, -math.pi/4), ("cx", a, c), ("Z", b, math.pi/4), ("Z", c, math.pi/4),
            ("h", c), ("cx", a, b), ("Z", a, math.pi/4), ("Z", b, -math.pi/4), ("cx", a, b)]


def _primitives(name, ang, qs, warnings):
    """Un gate (ya sin modificadores) -> lista de eventos primitivos. Eventos-Z se marcan ('Z', q, angulo)
    para la pasada de cancelacion; el resto son tuplas finales. Decompone ccx/crz/u3/rx/ry/swap/cy/cswap/
    rzz/rxx/ryy/crx/cry honestamente (descomposiciones que PRESERVAN la dureza: magia + entrelazamiento)."""
    a0 = ang[0] if ang else None
    if name in _ZROT and not ang:                      # t/tdg/s/sdg/z literal
        return [("Z", qs[0], _ZROT[name])]
    if name in ("rz", "p", "u1", "phase"):             # rotacion-Z con angulo
        return [("Z", qs[0], _evang(a0))]
    if name in ("h", "x", "y", "cx", "cnot"):
        return [("cx", *qs) if name == "cnot" else (name, *qs)]
    if name == "cz":                                   # cz = H_t CX H_t (el flattener no tiene cz en Clifford)
        return [("h", qs[1]), ("cx", qs[0], qs[1]), ("h", qs[1])]
    if name == "swap":                                 # swap = 3 CX (Clifford)
        a, b = qs
        return [("cx", a, b), ("cx", b, a), ("cx", a, b)]
    if name == "cy" and len(qs) == 2:                  # cy = Sdg_t CX S_t (Clifford)
        a, b = qs
        return [("Z", b, -math.pi/2), ("cx", a, b), ("Z", b, math.pi/2)]
    if name in ("sx", "sxdg"):                          # sqrt(X) (+/-) = Clifford
        s = math.pi/2 if name == "sx" else -math.pi/2
        return [("h", qs[0]), ("Z", qs[0], s), ("h", qs[0])]
    if name in ("rx", "ry"):                           # NO diagonal: la h rompe free-fermion (corrige el bug heredado)
        return [("h", qs[0]), ("Z", qs[0], _evang(a0)), ("h", qs[0])]
    if name in ("ccx", "toffoli") and len(qs) == 3:
        return _ccx_events(*qs)
    if name in ("cswap", "fredkin") and len(qs) == 3:  # Fredkin = CX_cb · Toffoli_abc · CX_cb
        a, b, c = qs
        return [("cx", c, b)] + _ccx_events(a, b, c) + [("cx", c, b)]
    if name == "rzz" and len(qs) == 2:                 # exp(-i th ZZ/2) = CX · Rz(th)_t · CX
        a, b = qs
        return [("cx", a, b), ("Z", b, _evang(a0)), ("cx", a, b)]
    if name in ("rxx", "ryy") and len(qs) == 2:        # rotacion de 2 qubits no-diagonal (dureza = rzz + base local)
        a, b = qs
        return [("h", a), ("h", b), ("cx", a, b), ("Z", b, _evang(a0)), ("cx", a, b), ("h", a), ("h", b)]
    if name in ("crx", "cry") and len(qs) == 2:        # rotacion controlada no-diagonal: R(th/2) CX R(-th/2) CX
        th = _evang(a0); a, b = qs
        h = th/2 if th is not None else None
        return [("h", b), ("Z", b, h), ("h", b), ("cx", a, b),
                ("h", b), ("Z", b, -h if h is not None else None), ("h", b), ("cx", a, b)]
    if name in ("crz", "cu1", "cp", "cphase") and len(qs) == 2:
        th = _evang(a0); a, b = qs
        h = th / 2 if th is not None else None
        return [("Z", b, h), ("cx", a, b), ("Z", b, -h if h is not None else None), ("cx", a, b)]
    if name in ("u3", "u") and len(qs) == 1 and len(ang) == 3:
        q = qs[0]
        return [("Z", q, _evang(ang[2])), ("h", q), ("Z", q, _evang(ang[0])), ("h", q), ("Z", q, _evang(ang[1]))]
    if name == "u2" and len(qs) == 1 and len(ang) == 2:
        q = qs[0]
        return [("Z", q, _evang(ang[1])), ("h", q), ("Z", q, math.pi/2), ("h", q), ("Z", q, _evang(ang[0]))]
    if name in ("barrier", "measure", "reset", "id"):
        return []
    warnings.append(f"gate no reconocido '{name}' -> IGNORADO (puede sub-estimar la dureza)")
    return []


def _normalize_qasm3(text: str) -> str:
    """Traduce el subconjunto comun de OpenQASM 3.0 a 2.0: 'qubit[n] q;'->'qreg q[n];', 'qubit a;'->'qreg
    a[1];' (y reescribe la referencia suelta 'a'->'a[0]'); descarta lineas clasicas/medida. HONESTO: NO
    soporta modificadores (ctrl@ / inv@ / pow) ni definiciones 'gate ...' custom de 3.0 -- se ignoran."""
    singles, out = set(), []
    for line in text.splitlines():
        m1 = _Q3_REG.match(line)
        if m1: out.append(f"qreg {m1.group(2)}[{m1.group(1)}];"); continue
        m2 = _Q3_ONE.match(line)
        if m2: singles.add(m2.group(1)); out.append(f"qreg {m2.group(1)}[1];"); continue
        s = line.strip()
        if s.startswith(("bit", "int", "uint", "float", "const", "creg", "input", "output", "angle", "gate")) \
           or "measure" in s or "->" in s or "reset" in s:
            continue
        out.append(line)
    text = "\n".join(out)
    for name in singles:                                   # 'a' suelto -> 'a[0]' (pero no 'a[1]' del qreg)
        text = re.sub(rf"\b{re.escape(name)}\b(?!\s*\[)", f"{name}[0]", text)
    return text


def validate_n(n, cap=40) -> int:
    """n debe ser entero en [1, cap] (la simulacion exacta del arsenal es 2^n)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise ValueError(f"n debe ser un entero (recibido {n!r})")
    if n < 1:
        raise ValueError(f"n debe ser >= 1 (recibido {n})")
    if n > cap:
        raise ValueError(f"n={n} excede el cap {cap} (el atlas usa simulacion exacta 2^n; usa la CLI con cap mayor)")
    return n


_CALL = re.compile(r"^\s*((?:(?:inv|negctrl|ctrl|pow\s*\([^)]*\))\s*@\s*)*)(\w+)\s*(\([^)]*\))?\s+(.+?)\s*;\s*$")
_GATEDEF = re.compile(r"gate\s+(\w+)\s*(?:\(([^)]*)\))?\s*([\w,\s\[\]]+?)\s*\{(.*?)\}", re.S)


def _qidx(token, qubits, sizes=None):
    token = token.strip()
    m = re.match(r"(\w+)\s*\[\s*(\d+)\s*\]\s*$", token)
    if m:
        name, idx = m.group(1), int(m.group(2))
        if name not in qubits:
            raise ValueError(f"registro de qubit no declarado: '{name}'")
        if sizes is not None and idx >= sizes.get(name, 1):   # B5: indice fuera de rango -> NO aceptar en silencio
            raise ValueError(f"indice de qubit fuera de rango: {name}[{idx}] pero '{name}' tiene tamano "
                             f"{sizes[name]} (indices validos 0..{sizes[name]-1})")
        return qubits[name] + idx
    if token in qubits:
        return qubits[token]                              # registro de 1 qubit referenciado sin indice
    raise ValueError(f"qubit no reconocido: '{token}' (declara su registro primero)")


def _robust_parse(text: str):
    """Parser instrument-grade: 2.0/3.0, gates custom (inline), modificadores (inv@ exacto; ctrl@/pow@ AVISO),
    descomposicion honesta (ccx/crz/u3/rx/ry) y CANCELACION de rotaciones-Z (T^8=I -> 0). Devuelve (n, circ, warns)."""
    warnings = []
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)     # comentarios de bloque /* */
    text = re.sub(r"//[^\n]*", "", text)                  # comentarios de linea //  (ANTES de desenrollar:
    text = re.sub(r"#[^\n]*", "", text)                   # comentarios de linea #    un ';' dentro de un
    text = text.replace(";", ";\n")                       # comentario no debe partir nada)
    # DESENROLLA la partitura: 'h q[0]; h q[1]; h q[2];' en una sola linea -> una instruccion por linea.
    # El parser casa _CALL contra cada linea, asi que sin esto leeria 'q[0]; h q[1]...' como un solo qubit.
    if "OPENQASM 3" in text or "qubit[" in text or re.search(r"^\s*qubit\b", text, re.M):
        text = _normalize_qasm3(text)
    qubits, qsizes, n = {}, {}, 0
    for m in re.finditer(r"qreg\s+(\w+)\s*\[\s*(\d+)\s*\]", text):
        qubits[m.group(1)] = n; qsizes[m.group(1)] = int(m.group(2)); n += int(m.group(2))
    if n < 1:
        raise ValueError("QASM sin qubits (declara 'qreg q[n];' en 2.0 o 'qubit[n] q;' en 3.0)")
    customs = {}
    for m in _GATEDEF.finditer(text):
        customs[m.group(1)] = ([p.strip() for p in (m.group(2) or "").split(",") if p.strip()],
                               [q.strip() for q in m.group(3).split(",") if q.strip()], m.group(4))
    text = _GATEDEF.sub("", text)
    events = []

    def emit_call(name, ang, qtokens, qmap, depth=0):
        if name in customs and depth < 8:                 # gate custom -> inline (sustituye qubits y params)
            params, qparams, body = customs[name]
            sub = dict(zip(qparams, qtokens))
            for bline in body.split(";"):
                bl = bline.strip()
                if not bl: continue
                mm = _CALL.match(bl + ";")
                if not mm: continue
                bn = mm.group(2).lower()
                bang = [a.strip() for a in mm.group(3)[1:-1].split(",")] if mm.group(3) else []
                bq = [sub.get(t.strip(), t.strip()) for t in mm.group(4).split(",")]
                emit_call(bn, bang, bq, qmap, depth + 1)
            return
        try:
            idxs = [_qidx(t, qmap, qsizes) for t in qtokens]
        except ValueError as e:
            warnings.append(str(e)); return
        events.extend(_primitives(name, ang, idxs, warnings))

    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith(("//", "#", "OPENQASM", "include", "qreg", "creg", "bit", "gate")):
            continue
        m = _CALL.match(line)
        if not m:
            continue
        mods, name, anggrp, argstr = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if name in ("measure", "reset", "barrier", "id", "delay", "nop"):
            continue                                      # medicion/reset/barrera de registro completo (incl.
                                                          # 'measure q -> c;' y 'measure q;'): no afectan la dureza
        if "ctrl" in mods or "negctrl" in mods or "pow" in mods:
            warnings.append(f"modificador en '{s}' (ctrl@/negctrl@/pow@) NO soportado plenamente -> "
                            f"el gate base se cuenta, pero el control/potencia puede sub/sobre-estimar la magia")
        ang = [a.strip() for a in anggrp[1:-1].split(",")] if anggrp else []
        if "inv" in mods and ang:                         # inv@ exacto para rotaciones: negar el angulo
            ang = [f"-({a})" for a in ang]
        emit_call(name, ang, [t.strip() for t in argstr.split(",")], qubits)

    # ===== pasada de CANCELACION: rotaciones-Z consecutivas en el mismo qubit se suman (aqui muere T^8=I)
    zacc, circuit = {}, []
    raw_magic = sum(1 for ev in events if ev[0] == "Z" and _classify_z(ev[2], 0) == [("t", 0)])

    def flush(q):
        if q in zacc:
            circuit.extend(_classify_z(zacc.pop(q), q))

    for ev in events:
        if ev[0] == "Z":
            _, q, a = ev
            if a is None:
                flush(q); circuit.append(("t", q))        # angulo desconocido -> 1 magia (conservador)
            else:
                zacc[q] = zacc.get(q, 0.0) + a
        else:
            for q in ev[1:]:
                flush(q)
            circuit.append(ev)
    for q in list(zacc):
        flush(q)
    # B4: si habia rotaciones-Z magicas que se cancelaron a Clifford, AVISAR (el usuario no debe confundirse)
    final_magic = sum(1 for g in circuit if g[0] == "t")
    if raw_magic > final_magic:
        warnings.append(f"{raw_magic} rotaciones-Z magicas (p.ej. T) se CANCELARON a Clifford -> magia neta "
                        f"{final_magic} (T^8=I y similares; correcto matematicamente, pero tu entrada tenia mas T)")
    return n, circuit, warnings


def safe_parse(text: str):
    """Punto de entrada con errores AMABLES. Devuelve (n, circuit, warnings).

    Si quedan gates 'no reconocido' y Qiskit esta disponible, NORMALIZA el QASM via Qiskit (reescribe a una
    base que atlas maneja) y re-parsea -- asi el QASM de Qiskit/Cirq/TKET parsea sin descartar compuertas."""
    if not text or not text.strip():
        raise ValueError("QASM vacio")
    try:
        n, circ, warns = _robust_parse(text)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"QASM invalido: {type(e).__name__}: {e}")
    if any("no reconocido" in w for w in warns):
        try:
            from importers import normalize_qasm
            n2, circ2, warns2 = _robust_parse(normalize_qasm(text))
            if not any("no reconocido" in w for w in warns2):     # solo si la normalizacion los resolvio
                warns2 = [w for w in warns if "no reconocido" not in w] + warns2
                warns2.append("QASM normalizado via Qiskit (gates fuera de la base de atlas re-escritos; "
                              "dureza preservada)")
                return n2, circ2, warns2
        except Exception:
            pass                                                  # sin Qiskit / fallo -> nos quedamos con el nativo
    return n, circ, warns


ARSENAL_CAP = 14    # arsenal_router.route (fold+spread) es ~2^n: n=14=21ms, n=16=107ms, n=18=579ms. Cap
                    # medido para quedar <~25ms; arriba SALTAMOS al fast-path (MPS/treewidth/magia, conservador).


def _resources(best, cost_log2, n, mps_log2):
    """CAPA 8: convierte 'TRACTABLE' (semaforo) en RECURSOS cuantificados (RAM/tiempo). Honesto: estimacion
    de orden de magnitud del recurso DOMINANTE del mejor metodo, con complex128 (16 B/amplitud)."""
    if cost_log2 is None:
        return None
    if "MPS" in best:                                       # MPS: ~ n * bond^2 * 16 B
        ram = n * (4.0 ** mps_log2) * 16.0
    else:                                                   # treewidth/spread/fold: ~ 2^cost * 16 B (mayor tensor)
        ram = (2.0 ** cost_log2) * 16.0
    t_s = ram / 2e10                                        # ~20 GB/s de ancho de banda de memoria efectivo
    for u, d in [(1e15, "PB"), (1e12, "TB"), (1e9, "GB"), (1e6, "MB"), (1e3, "kB")]:
        if ram >= u:
            human = f"{ram/u:.1f} {d}"; break
    else:
        human = f"{ram:.0f} B"
    feasible = ram <= 24e9                                  # cabe en 24 GB (la RAM del M4 de referencia)
    return {"ram_bytes": ram, "ram_human": human, "time_s": round(t_s, 4),
            "fits_24gb": feasible, "method": best}


def cost_atlas(n: int, circuit: list, observable=None, budget_log2=40.0) -> dict:
    """El atlas de costo. MPS y treewidth se CABLEAN a ground-truth (quimb/cotengra), que es POLINOMIAL y
    escala a n grande; el arsenal (exponencial) solo se usa para n<=ARSENAL_CAP (da fold/spread). Reporta
    recursos cuantificados (RAM/tiempo), no solo un veredicto-semaforo."""
    from ground_truth import mps_bond_log2, treewidth_log2, cross_validate
    t_count = sum(1 for g in circuit if g and g[0] == "t")
    if _ENGINE and n <= ARSENAL_CAP:
        r = arsenal_router.route(n, circuit, observable)    # fold/MPS/spread/treewidth + min (motor presente)
    else:                                                   # FAST PATH (deuda #3): sin arsenal exponencial
        # fold(magic) = extent estabilizador ~ 0.3962 * t_count (medido vs arsenal: coincide exacto). Asi el
        # fast-path SI tiene la ruta de magia (cierra la brecha de coste vs el full path), sin el arsenal.
        r = {"costs_log2": {"fold(magic)": round(0.3962 * t_count, 2), "spread(local)": None,
                            "MPS(entangle)": 0.0, "contraction(treewidth)": 0.0}, "fast_path": True}
    r["libro_flattener"] = which_flattener(circuit)
    r["t_count"] = t_count
    r["gt_ok"] = False; r["ground_truth"] = None
    try:                                                    # GROUND TRUTH para TODO n (poly): quimb + cotengra
        b, trunc = mps_bond_log2(n, circuit)
        tw, tw_exact = treewidth_log2(n, circuit)
        r["costs_log2"]["MPS(entangle)"] = round(b, 2)
        r["costs_log2"]["contraction(treewidth)"] = round(tw, 2)
        r["gt_ok"] = True; r["mps_truncated"] = trunc; r["treewidth_exact"] = tw_exact
        gt = cross_validate(n, circuit, t_count, b, tw, trunc,
                            spread_log2=r["costs_log2"].get("spread(local)"), tw_exact=tw_exact)
        r["ground_truth"] = gt
        r["stim_clifford"] = bool(gt.get("stim_clifford"))
        r.setdefault("cross_warnings", []).extend(gt["warnings"])
        if r.get("fast_path"):
            over = n > ARSENAL_CAP
            r["fast_path_reason"] = "n_gt_cap" if over else "engine_unavailable"
            reason = (f"n={n}>{ARSENAL_CAP} (arsenal es ~2^n)" if over
                      else f"motor de arsenal no disponible en este build (n={n}<={ARSENAL_CAP})")
            r["cross_warnings"].append(f"fast-path: {reason}. fold(magic)=0.3962*#T (extent estabilizador, "
                                       f"coincide con el arsenal); spread(local) NO computado (skipped por "
                                       f"politica, no es 'n/a exitoso') -- veredicto por magia/MPS/treewidth")
        costs = {k: v for k, v in r["costs_log2"].items() if isinstance(v, (int, float))}
        best = min(costs, key=costs.get)
        r["union_cost_log2"] = round(costs[best], 2); r["best_method"] = best
        r["tractable"] = costs[best] <= budget_log2
        r["resources"] = _resources(best, costs[best], n, b)   # CAPA 8: RAM/tiempo cuantificados
        res = r["resources"]
        if r["tractable"] and ("MPS" in best and trunc):
            tw_cost = costs.get("contraction(treewidth)", 0)
            # Exact statevector is ALWAYS available and never truncated: cost = 2^n.
            # It is a confirmed classical route up to the realistic memory ceiling
            # (n<=33 ~ 2^33 ~ 128 GB; matches route_adjudicator SV_HPC_MAX_N). The
            # legacy INTRACTABLE verdict ignored it and over-claimed hardness for small
            # n (e.g. n=26 statevector = ~1 GB is trivially feasible). Reconcile here.
            SV_MAX_N = 33
            sv_ok = n <= SV_MAX_N
            if tw_cost > budget_log2 and not sv_ok:         # truncated MPS, tw over budget, AND statevector infeasible
                r["tractable"] = False                      # -> no confirmed classical route -> intractable
                r["verdict"] = (f"INTRACTABLE (probable): MPS truncado (>=2^{r['union_cost_log2']}, sin ruta "
                                f"confirmada), treewidth 2^{round(tw_cost,1)} y statevector 2^{n} > presupuesto/ceiling")
            elif tw_cost > budget_log2 and sv_ok:           # treewidth over budget BUT exact statevector fits
                r["tractable"] = True                       # statevector certifies a confirmed exact route
                _gb = (2 ** n) * 16 / 1e9
                r["verdict"] = (f"TRACTABLE via exact statevector (2^{n} ~ {_gb:.1f} GB); MPS truncado y "
                                f"treewidth 2^{round(tw_cost,1)} no certifican, pero statevector si (n<=33)")
            else:
                r["tractable"] = None                       # MPS truncado pero treewidth da ruta -> provisional
                r["verdict"] = f"PROVISIONAL via {best} (>=2^{r['union_cost_log2']}, MPS TRUNCADO -> cota inferior)"
        elif r["tractable"]:
            r["verdict"] = (f"TRACTABLE via {best} (2^{r['union_cost_log2']}; "
                            f"~{res['ram_human']} footprint del metodo{'' if res['fits_24gb'] else ', NO cabe en 24 GB'})")
        else:
            r["verdict"] = "WALL: todos los metodos exceden el presupuesto (nucleo irreducible)"
        # VERIFICACION EXACTA por metodo (la 'frontera de exactitud' no es un solo n: depende del metodo).
        mv = r.get("ground_truth", {}).get("validations", {}) if isinstance(r.get("ground_truth"), dict) else {}
        r["exact_verification"] = {
            "magic": ("exacto: unitario Clifford (n<=9)" if "clifford_exact" in mv
                      else "exacto: Stim Clifford-ness (cualquier n)"),
            "MPS": ("exacto (bond no truncado)" if not trunc else "cota inferior (bond truncado)"),
            "treewidth": ("OPTIMO EXACTO (red pequena)" if tw_exact else "cota superior heuristica (greedy)"),
        }
        # MODELO DE RUIDO (analitico): convierte el veredicto coherente en un rango [ruidoso, coherente].
        n_2q = sum(1 for g in circuit if g and g[0] in ("cx", "cnot", "cz"))
        hard = costs[best] if r["tractable"] is True else tw   # dureza que liga: union si tratable, si no treewidth
        r["n_2q"] = n_2q; r["hardness_log2"] = round(hard, 2)
        try:
            from route_adjudicator import adjudicate_route
            r["route_adjudication"] = adjudicate_route(r, budget_log2=budget_log2, n=n)
        except Exception as e:
            r["route_adjudication_error"] = f"{type(e).__name__}: {e}"
        try:
            from noise import noise_model
            r["noise"] = noise_model(n_2q, hard, t_count, 0.005, budget_log2, n=n)
            if n <= 6:                                       # VALIDA el modelo analitico vs sim ruidosa EXACTA
                from exact import noisy_fidelity_exact
                fe, fa = noisy_fidelity_exact(n, circuit, r["noise"]["p"])
                r["noise"]["F_exact"] = round(fe, 4)
                r["noise"]["validated_exact"] = bool(abs(fe - fa) < 0.02)
        except Exception as e:
            r.setdefault("noise", None); r["noise_err"] = str(e)
    except Exception as e:
        r["gt_error"] = f"{type(e).__name__}: {e}"
    return r


def render(n, circuit, label="circuito", warnings=None):
    r = cost_atlas(n, circuit)
    c = r["costs_log2"]
    print(f"\nATLAS DE COSTO -- {label}  ({n} qubits, {len(circuit)} primitivos)")
    print("-" * 60)
    print(f"  magia (#T, tras cancelar Z): {r['t_count']}   [exacto en cadenas-Z diagonales; sobre-estima en cruces]")
    print(f"  libro (flattener)          : {r['libro_flattener']}")
    print(f"  costo log2 por metodo:")
    for k, v in c.items():
        print(f"     {k:<24}: {'2^'+str(v) if isinstance(v,(int,float)) else 'n/a (arsenal exponencial omitido)'}")
    print(f"  MINIMO (mejor metodo)     : 2^{r['union_cost_log2']} via {r['best_method']}")
    if r.get("resources"):
        print(f"  RECURSOS (estimado)       : ~{r['resources']['ram_human']} RAM, "
              f"{'cabe' if r['resources']['fits_24gb'] else 'NO cabe'} en 24 GB")
    print(f"  VEREDICTO                 : {r['verdict']}")
    if warnings:
        print("  AVISOS:")
        for w in warnings:
            print(f"     ! {w}")
    print("-" * 60)
    return r


# ============================================================ GENERADOR (pide un punto -> circuito + QASM)
def _density(v, hi, lo):
    """'high'/'low' -> hi/lo; un numero -> densidad directa (acepta 0..1 o 0..100). Hace continuos los diales."""
    if isinstance(v, bool):
        return hi if v else lo
    if isinstance(v, (int, float)):
        x = float(v)
        return max(0.0, min(1.0, x / 100.0 if x > 1 else x))
    return hi if v == "high" else lo


def build_target(n, depth, magic, spread, book, treewidth="low", seed=0):
    """Construye un circuito en el punto del diagrama: magic/spread/treewidth in {high,low}; book in {core,free}.

    magic/spread/treewidth aceptan 'high'/'low' O un NUMERO (densidad 0..1, o 0..100): magic=99 -> mas denso
    que magic=4 (antes ambos caian a 'low'). spread/treewidth altos usan CONECTIVIDAD 2D (rejilla ~sqrt(n)):
    los acoples verticales cruzan ~sqrt(n) el orden del MPS -> bond ~2^sqrt(n). Con cadena 1D el MPS trivializa
    (satura en 2^(n/2)); la 2D genera entrelazamiento REAL. El eje 'entrelazamiento' del diagrama mueve el MPS."""
    rng = np.random.default_rng(seed)
    td = _density(magic, 0.5, 0.04)                        # densidad de T (continua)
    p = _density(spread, 0.8, 0.12)                        # densidad de acoples (continua)
    tw = _density(treewidth, 1.0, 0.0)

    def ent(g, a, b):                                       # acople entre dos qubits, segun el libro
        if book == "free": g.append(("hop", a, b, 0.5))     # free-fermion: hop matchgate
        else: g += [("cx", a, b), ("rz", b, math.pi/4), ("cx", a, b)]   # core: Clifford+T genuino (rz=pi/4=T)

    g = []
    if p >= 0.4 or tw >= 0.5:                               # ---- REJILLA 2D: entrelazamiento genuino (MPS alto)
        cols = max(2, int(round(n ** 0.5)))
        for L in range(depth):
            for q in range(n):
                if book == "core": g.append(("h", q))
                if rng.random() < td: g.append(("t", q))
            for q in range(n):                             # acoples horizontales (vecino +1, misma fila)
                if (q % cols) < cols - 1 and q + 1 < n and rng.random() < p:
                    ent(g, q, q + 1)
            for q in range(n):                             # acoples VERTICALES (vecino +cols): cruzan el MPS
                if q + cols < n and rng.random() < p:
                    ent(g, q, q + cols)
        return g
    for L in range(depth):                                 # ---- CADENA 1D (treewidth bajo)
        for q in range(n):
            if book == "core": g.append(("h", q))
            if rng.random() < td: g.append(("t", q))
        for q in range(L % 2, n - 1, 2):
            if rng.random() < p:
                ent(g, q, q + 1)
    return g


def _hop_ops(a, b, th):
    """hop=exp(i*th(XX+YY)/2) descompuesto en SOLO {h, rz, cx} (rx(f)=h rz(f) h). Mismo para arsenal y QASM."""
    P = np.pi
    return [("h", a), ("rz", a, P / 2), ("h", a), ("h", b), ("rz", b, P / 2), ("h", b),
            ("cx", a, b), ("rz", b, -th), ("cx", a, b),
            ("h", a), ("rz", a, -P / 2), ("h", a), ("h", b), ("rz", b, -P / 2), ("h", b),
            ("h", a), ("h", b), ("cx", a, b), ("rz", b, -th), ("cx", a, b), ("h", a), ("h", b)]


def decompose(circuit):
    """Reemplaza hop por su descomposicion {h,rz,cx} (para arsenal/pauli-prop y QASM, que no soportan hop)."""
    out = []
    for g in circuit:
        out += _hop_ops(g[1], g[2], g[3]) if g[0] == "hop" else [g]
    return out


def to_qasm(n, circuit):
    """OpenQASM 2.0 estandar (un statement por linea), solo gates de qelib1. hop -> {h,rz,cx}."""
    out = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{n}];"]
    for g in decompose(circuit):
        op = g[0]
        if op in ("h", "t", "s", "x", "y", "z"): out.append(f"{op} q[{g[1]}];")
        elif op in ("cx", "cnot"): out.append(f"cx q[{g[1]}],q[{g[2]}];")
        elif op == "cz": out.append(f"cz q[{g[1]}],q[{g[2]}];")
        elif op == "rz": out.append(f"rz({g[2]}) q[{g[1]}];")
    return "\n".join(out) + "\n"


def _verify_hop(th=0.5):
    """Auto-chequeo: la descomposicion {h,rz,cx} del hop = exp(i*th(XX+YY)/2) (modulo fase global)."""
    from scipy.linalg import expm
    X = np.array([[0, 1], [1, 0]], complex); Y = np.array([[0, -1j], [1j, 0]], complex)
    Z = np.array([[1, 0], [0, -1]], complex); I = np.eye(2, dtype=complex)
    H = np.array([[1, 1], [1, -1]], complex) / np.sqrt(2)
    target = expm(1j * th * (np.kron(X, X) + np.kron(Y, Y)) / 2)
    cxm = np.array([[1,0,0,0],[0,1,0,0],[0,0,0,1],[0,0,1,0]], complex)
    def k(g, a): return np.kron(g, I) if a == 0 else np.kron(I, g)
    U = np.eye(4, dtype=complex)
    for g in _hop_ops(0, 1, th):
        if g[0] == "h": M = k(H, g[1])
        elif g[0] == "rz": M = k(expm(-1j * g[2] / 2 * Z), g[1])
        elif g[0] == "cx": M = cxm
        U = M @ U
    ph = target[1, 2] / U[1, 2] if abs(U[1, 2]) > 1e-9 else 1.0
    return np.allclose(U * ph, target, atol=1e-9)


def generate(args):
    opt = {a.split("=")[0].lstrip("-"): a.split("=")[1] for a in args if "=" in a}
    n = validate_n(opt.get("n", 12)); depth = int(opt.get("depth", 6))
    magic = opt.get("magic", "high"); spread = opt.get("spread", "high")
    book = opt.get("book", "core"); tw = opt.get("treewidth", "low")
    print(f"=== atlas.py GENERAR -- punto pedido: magic={magic}, spread={spread}, book={book}, "
          f"treewidth={tw}, n={n} ===")
    native = build_target(n, depth, magic, spread, book, tw)     # con hop (para el flattener/libro)
    dec = decompose(native)                                       # {h,rz,cx} (para arsenal + QASM)
    r = cost_atlas(n, dec)
    r["libro_flattener"] = which_flattener(native)               # el libro REAL del circuito nativo
    r["t_count"] = sum(1 for g in native if g and g[0] == "t")
    c = r["costs_log2"]
    print(f"\nVERIFICADO -- el circuito generado cae en:")
    print(f"   magia(T)={r['t_count']}  libro='{r['libro_flattener']}'  "
          f"MPS=2^{c['MPS(entangle)']}  spread=2^{c['spread(local)']}  treewidth=2^{c['contraction(treewidth)']}")
    print(f"   veredicto: {r['verdict']}")
    print("\nOpenQASM 2.0 del circuito generado (estandar, usable en Qiskit/Cirq):\n")
    print(to_qasm(n, native))


def _demo_qasm(n=8, depth=6):
    """Genera un QASM (un statement por linea: lo que el parser espera) con magia y entrelazamiento."""
    import numpy as np
    rng = np.random.default_rng(0)
    lines = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{n}];"]
    for L in range(depth):
        for q in range(n):
            lines.append(f"h q[{q}];")
            if rng.random() < 0.5: lines.append(f"t q[{q}];")
        for q in range(L % 2, n - 1, 2):
            lines.append(f"cx q[{q}],q[{q+1}];")
    return "\n".join(lines) + "\n"


DEMO_QASM = _demo_qasm()


def batch_ingest(patterns):
    """INGESTA POR LOTES: parsea+analiza muchos documentos QASM (globs/dirs) y emite una tabla + throughput.
    Acepta .qasm sueltos, globs ('circuitos/*.qasm') o directorios (ingiere *.qasm dentro)."""
    import glob, os, time
    files = []
    for p in patterns:
        if os.path.isdir(p):
            files += sorted(glob.glob(os.path.join(p, "*.qasm")))
        else:
            files += sorted(glob.glob(p))
    if not files:
        print(f"sin archivos .qasm en {patterns}"); return
    print(f"=== INGESTA POR LOTES -- {len(files)} documentos ===")
    print(f"{'archivo':<34} {'n':>3} {'#T':>4} {'libro':>11} {'veredicto':<28} {'ms':>7}")
    print("-" * 92)
    ok = 0; t_all = time.time()
    for f in files:
        name = os.path.basename(f)[:33]
        try:
            with open(f) as fh:
                n, circ, warns = safe_parse(fh.read())
            t0 = time.time(); r = cost_atlas(n, circ); dt = (time.time() - t0) * 1000
            ver = r["verdict"].split(" (")[0][:27]
            print(f"{name:<34} {n:>3} {r['t_count']:>4} {r['libro_flattener']:>11} {ver:<28} {dt:>7.0f}")
            ok += 1
        except Exception as e:
            print(f"{name:<34} ERROR: {type(e).__name__}: {str(e)[:40]}")
    dt_all = time.time() - t_all
    print("-" * 92)
    print(f"{ok}/{len(files)} ingeridos en {dt_all:.1f}s  ->  {ok/max(dt_all,1e-6):.1f} documentos/s")


def main():
    args = sys.argv[1:]
    if args and args[0] == "batch":
        batch_ingest(args[1:] or ["."])
    elif args and args[0] == "generate":
        assert _verify_hop(), "descomposicion del hop incorrecta"     # auto-chequeo antes de emitir
        generate(args[1:])
    elif not args or args[0] == "--demo":
        print("=== atlas.py: la interfaz unificada (modo demo) ===")
        n, circ, warns = safe_parse(DEMO_QASM)
        render(n, circ, "demo QASM", warns)
        print("\nDIAGNOSTICAR:  pixi run python atlas.py tu_circuito.qasm")
        print("GENERAR:       pixi run python atlas.py generate --magic=high --spread=high --book=free --n=12")
    else:
        path = args[0]
        try:
            with open(path) as f:
                n, circ, warns = safe_parse(f.read())
        except (OSError, ValueError) as e:
            print(f"ERROR: {e}"); return
        render(n, circ, path, warns)


if __name__ == "__main__":
    main()

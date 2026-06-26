#!/usr/bin/env python3
"""adversarial_attack — herramienta OFENSIVA (red-team) contra el clasificador de Atlas.

Objetivo explícito: ENGAÑAR al adjudicador (que rute barato algo caro = falsa-seguridad, o caro algo
barato = falsa-alarma), EXPLOTAR las heurísticas (el modelo de coste statevector ignora la profundidad;
treewidth greedy es cota superior; magia=0.3962·#T), y SATURAR los motores (quimb/cotengra/Stim) durante
el propio triage. Corre el pipeline REAL (atlas.cost_atlas + route_adjudicator.adjudicate_route) y, donde
es factible (n<=22), el ground-truth statevector CRONOMETRADO. Reporta hallazgos por severidad para endurecer.

No genera nada destructivo: solo construye circuitos QASM y mide. Uso: python3 benchmarks/adversarial_attack.py
"""
from __future__ import annotations
import os, sys, time, random, signal, json, traceback

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))

from atlas import safe_parse, cost_atlas                       # noqa: E402
from atlas_timeout import cost_atlas_guarded                   # noqa: E402  (path de producción, hijo killable)
from route_adjudicator import adjudicate_route, CPU_TW_MAX, CPU_MPS_MAX, SV_CPU_MAX_N  # noqa: E402
from ground_truth import compute_result                        # noqa: E402

GUARD_S = 10.0          # budget del triage guarded; compute_bound=True => el cost_atlas crudo colgaría (DoS-class)

# presupuestos que el clasificador IMPLÍCITAMENTE promete por ruta (segundos de pared)
CPU_PROMISE_S = 1.5      # "CPU" promete <~1s; damos margen
TENSOR_PROMISE_S = 60.0  # "TENSOR" promete ~<60s
TRIAGE_BUDGET_S = 8.0    # el triage en sí debería ser interactivo (<~8s); más = DoS del triage
HARD_CAP_S = 45          # tope duro por fase (señal) para no colgar el red-team


class _Timeout(Exception):
    pass


class deadline:
    """Tope de pared por fase vía SIGALRM (Unix, hilo principal)."""
    def __init__(self, sec): self.sec = int(sec)
    def __enter__(self):
        signal.signal(signal.SIGALRM, self._fire); signal.alarm(self.sec)
    def __exit__(self, *a): signal.alarm(0)
    def _fire(self, *a): raise _Timeout()


# ---------- generadores de circuitos adversarios (QASM) ----------
def gen_deep(n, depth, seed, clifford=False):
    """Brickwork denso: capas 1q + cx alternadas. Profundo = muchas compuertas (ataca el coste-por-n)."""
    rng = random.Random(seed)
    L = ["OPENQASM 2.0;", 'include "qelib1.inc";', "qreg q[%d];" % n, "creg c[%d];" % n]
    g1 = ["h", "s"] if clifford else ["h", "s", "t", "tdg"]
    for d in range(depth):
        for q in range(n):
            L.append("%s q[%d];" % (rng.choice(g1), q))
        for q in range(d % 2, n - 1, 2):
            L.append("cx q[%d],q[%d];" % (q, q + 1))
    return "\n".join(L) + "\n"


def gen_longrange(n, depth, seed):
    """cx de largo alcance (q0<->q_{n-1}, etc.): intenta inflar el treewidth greedy (¿falsa-alarma?)."""
    rng = random.Random(seed)
    L = ["OPENQASM 2.0;", 'include "qelib1.inc";', "qreg q[%d];" % n, "creg c[%d];" % n]
    for d in range(depth):
        for q in range(n):
            L.append("%s q[%d];" % (rng.choice(["h", "t", "s"]), q))
        for _ in range(n // 2):
            a, b = rng.sample(range(n), 2)
            L.append("cx q[%d],q[%d];" % (a, b))
    return "\n".join(L) + "\n"


def gen_magic_cancel(n, pairs, seed):
    """t seguido de tdg (magia neta CERO) repetido: infla #T sin magia real -> ¿falsa-alarma de magia?"""
    rng = random.Random(seed)
    L = ["OPENQASM 2.0;", 'include "qelib1.inc";', "qreg q[%d];" % n, "creg c[%d];" % n]
    for q in range(n):
        L.append("h q[%d];" % q)
    for _ in range(pairs):
        q = rng.randrange(n)
        L.append("t q[%d];" % q); L.append("tdg q[%d];" % q)   # cancelan: estado = Clifford
    for q in range(n - 1):
        L.append("cx q[%d],q[%d];" % (q, q + 1))
    return "\n".join(L) + "\n"


# ---------- harness: corre el pipeline real y clasifica el hallazgo ----------
def attack(qasm, label, family):
    rec = {"label": label, "family": family, "findings": [], "severity": "ok"}
    try:
        n, circ, _ = safe_parse(qasm)
    except Exception as e:
        rec["findings"].append("parse_error: " + repr(e)); rec["severity"] = "info"; return rec
    rec["n"] = n; rec["gates"] = len(circ)
    # 1) TRIAGE por el path de PRODUCCIÓN (cost_atlas_guarded): hijo killable. Si excede el budget,
    #    devuelve compute_bound=True -> eso PRUEBA que el cost_atlas crudo colgaría (DoS-class input).
    t0 = time.time()
    try:
        res = cost_atlas_guarded(n, circ, timeout_s=GUARD_S)
    except Exception as e:
        rec["findings"].append("triage_CRASH: " + repr(e)[:160]); rec["severity"] = "HIGH"; return rec
    triage_s = time.time() - t0
    rec["triage_s"] = round(triage_s, 2)
    if res.get("compute_bound"):
        rec["findings"].append("DoS-class: el cost_atlas CRUDO colgaría >%.0fs (cuelgue en C). "
                               "El guard degradó a HPC_FIRST honesto -> servidor protegido." % GUARD_S)
        rec["severity"] = max_sev(rec["severity"], "MED")
    adj = res.get("route_adjudication")
    if not adj:
        try:
            adj = adjudicate_route(res, n=n)
        except Exception as e:
            rec["findings"].append("adjudicate_CRASH: " + repr(e)[:160]); rec["severity"] = "HIGH"; return rec
    route = adj.get("route"); rec["route"] = route
    rec["governing"] = adj.get("governing_estimator"); rec["conf"] = (adj.get("confidence") or {}).get("score")
    rec["mps_trunc"] = bool(res.get("mps_truncated")); rec["tw_exact"] = bool(res.get("treewidth_exact"))
    # 2) GROUND TRUTH cronometrado (statevector exacto si n<=22) -> ¿la realidad contradice la ruta?
    # Ground-truth SOLO donde podría haber falsa-seguridad: ruta barata (CPU/TENSOR) y tamaño factible.
    # Si ya rutea HPC/ESCALATE (o degradó), no hay falsa-seguridad que verificar -> sáltalo (rápido).
    comp_s = None
    if n <= 22 and route in ("CPU", "TENSOR") and len(circ) <= 4000:
        t1 = time.time()
        try:
            with deadline(HARD_CAP_S):
                comp = compute_result(n, circ, res.get("t_count", 0))
            comp_s = time.time() - t1
            rec["computed"] = bool(comp.get("computed"))
        except _Timeout:
            comp_s = float("inf")
        except Exception as e:
            rec["findings"].append("compute_CRASH: " + repr(e)[:120])
    rec["compute_s"] = (round(comp_s, 2) if comp_s not in (None, float("inf")) else ("inf" if comp_s == float("inf") else None))

    # ---- clasificación de hallazgos ----
    # A) triage lento = DoS interactivo
    if triage_s > TRIAGE_BUDGET_S:
        rec["findings"].append("triage_slow: %.1fs (>%.0fs interactivo)" % (triage_s, TRIAGE_BUDGET_S))
        rec["severity"] = max_sev(rec["severity"], "MED")
    # B) FALSA-SEGURIDAD: ruta barata pero la entrega real es cara/no termina
    promise = CPU_PROMISE_S if route == "CPU" else (TENSOR_PROMISE_S if route == "TENSOR" else None)
    if promise is not None and comp_s is not None:
        if comp_s == float("inf"):
            rec["findings"].append("FALSE_SECURITY: ruta=%s pero el statevector real no terminó en %ds" % (route, HARD_CAP_S))
            rec["severity"] = "HIGH"
        elif comp_s > promise:
            rec["findings"].append("FALSE_SECURITY: ruta=%s (promete <%.1fs) pero el cómputo real tardó %.1fs"
                                   % (route, promise, comp_s))
            rec["severity"] = "HIGH"
    return rec


def max_sev(a, b):
    order = {"ok": 0, "info": 1, "MED": 2, "HIGH": 3}
    return a if order.get(a, 0) >= order.get(b, 0) else b


def main():
    cases = []
    print("=== red-team Atlas: generando ataques ===")
    # Familia 1 — statevector ignora profundidad: n fijo (ruta SV=CPU), profundidad creciente.
    for n in (18, 20):
        for depth in (40, 160, 640, 2560):
            cases.append((gen_deep(n, depth, seed=100 + depth, clifford=False),
                          "deep_sv n=%d D=%d" % (n, depth), "sv_depth"))
    # Familia 2 — saturar el triage (quimb/cotengra) con densidad+profundidad cerca del cap de bond.
    for n in (21, 22):
        for depth in (200, 800):
            cases.append((gen_deep(n, depth, seed=7, clifford=False), "triage_dos n=%d D=%d" % (n, depth), "triage_dos"))
    # Familia 3 — Stim saturation: Clifford grande y profundo.
    for n in (30, 48):
        cases.append((gen_deep(n, 400, seed=3, clifford=True), "stim_sat clifford n=%d" % n, "stim_sat"))
    # Familia 4 — treewidth greedy gap (largo alcance) -> ¿falsa-alarma?
    for n in (16, 20):
        cases.append((gen_longrange(n, 30, seed=5), "tw_longrange n=%d" % n, "tw_gap"))
    # Familia 5 — magia cancelada (t·tdg): infla #T, magia real cero.
    cases.append((gen_magic_cancel(10, 60, seed=9), "magic_cancel n=10", "magic"))

    results = []
    for qasm, label, fam in cases:
        print("  · %-26s ..." % label, end="", flush=True)
        r = attack(qasm, label, fam)
        results.append(r)
        tag = r["severity"] if r["severity"] != "ok" else "ok"
        print(" [%s] route=%s triage=%ss compute=%ss" % (tag, r.get("route", "?"), r.get("triage_s", "?"), r.get("compute_s", "?")))

    findings = [r for r in results if r["severity"] in ("HIGH", "MED")]
    print("\n=== HALLAZGOS (%d de %d casos) ===" % (len(findings), len(results)))
    for r in sorted(findings, key=lambda x: max_sev("ok", x["severity"]), reverse=True):
        print(" [%s] %s (n=%s, %s gates):" % (r["severity"], r["label"], r.get("n"), r.get("gates")))
        for f in r["findings"]:
            print("      - " + f)
    out = os.path.join(ROOT, "benchmarks", "adversarial_findings.json")
    json.dump(results, open(out, "w"), indent=2, default=str)
    print("\n-> %s" % out)
    highs = [r for r in results if r["severity"] == "HIGH"]
    print("RESUMEN: %d HIGH (falsa-seguridad / DoS / crash), %d MED." %
          (len(highs), len([r for r in results if r["severity"] == "MED"])))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""The Spend Frontier — Atlas's signature economics exhibit (REAL DATA ONLY).

Every point on the chart is a REAL named circuit from the external corpus
(benchmarks/external_corpus/, 4 results.json, dedup by name) with:
  x  = the engine's STORED governing classical cost (log2 units, from each
       circuit's adjudicated `governing_cost_log2`),
  y1 = the classical route cost in $ from deploy/app/economics.py (the SAME
       module the live verdict uses): MEASURED quimb-MPS sim time for
       TRACTABLE circuits (offline, so the web-only MEAS_N_CAP guard is
       lifted — the module itself documents "el sim grande se mide offline"),
       or the module's HPC flops model for WALL (non-tractable) circuits,
  y2 = the QPU alternative cost in $ from economics.qpu_cost() with the
       module's defaults (eps=1e-2 casual precision, DEFAULT_VENDOR =
       IonQ Forte on AWS Braket, published dated pricing), with the
       exponential PEC mitigation overhead e^(4*eps_g*n2q) where n2q is the
       two-qubit gate count of the circuit parsed by the engine's own
       safe_parse (same decomposition the live site applies).

ESCALATE circuits get NO classical price (that is the story). Circuits whose
numbers cannot be computed honestly are EXCLUDED and logged in the JSON.

Usage:
  .atlas-venv/bin/python generate_spend_frontier.py            # compute (sequential) + render
  .atlas-venv/bin/python generate_spend_frontier.py --shard 0/4   # compute shard 0 of 4 -> spend_frontier.shard0.json
  .atlas-venv/bin/python generate_spend_frontier.py --merge 4     # merge 4 shards + render
  .atlas-venv/bin/python generate_spend_frontier.py --render-only # re-render SVGs from existing JSON

NO deploy, NO git: writes only benchmarks/spend_frontier/*.{json,svg} and the
final SVGs additionally to deploy/app/site/.
"""
from __future__ import annotations
import json
import math
import os
import signal
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
APP = os.path.join(REPO, "deploy", "app")
CORPUS = os.path.join(REPO, "benchmarks", "external_corpus")
SITE = os.path.join(APP, "site")
OUT_JSON = os.path.join(HERE, "spend_frontier.json")

# The 4 corpus batches, in dedup priority order (first occurrence of a name wins).
BATCHES = [
    (os.path.join(CORPUS, "results.json"), os.path.join(CORPUS, "qasm")),
    (os.path.join(CORPUS, "tier2_vqe", "results.json"), os.path.join(CORPUS, "tier2_vqe", "qasm")),
    (os.path.join(CORPUS, "batch2_published", "results.json"), os.path.join(CORPUS, "batch2_published", "qasm")),
    (os.path.join(CORPUS, "tier2_qaoa_trotter", "results.json"), os.path.join(CORPUS, "tier2_qaoa_trotter", "qasm")),
]

EPS = 0.01              # casual precision — the module/webui default
SIM_BUDGET_S = 900      # per-circuit wall-clock cap for the measured MPS sim
OFFLINE_MEAS_N_CAP = 400  # lift the web-server-only guard: measure ALL tractable sims offline

# ---------------------------------------------------------------------------
# palette (validated with dataviz validate_palette.js on surface #0b0b13,
# mode dark: lightness band PASS, chroma PASS, CVD PASS even all-pairs
# (worst ΔE 24.0 deutan), contrast PASS). Snapped from the site colors
# #48bb78/#7dd3fc/#f6ad55/#fb7185 which FAIL on dark (deutan ΔE 2.3).
# ---------------------------------------------------------------------------
PALETTE = {"CPU": "#2d8949", "TENSOR": "#4d9cd0", "HPC_FIRST": "#c8831e", "ESCALATE": "#ae316e"}
ROUTE_ORDER = ["CPU", "TENSOR", "HPC_FIRST", "ESCALATE"]
SURFACE = "#0b0b13"
INK = "#e2e8f0"
INK2 = "#94a3b8"
INK3 = "#5b6474"       # muted/axis
GRID = "#1a1f2e"
QPU_GRAY = "#8b93a5"   # neutral muted gray for QPU-alternative hollow markers


class _Timeout(Exception):
    pass


def _alarm(_sig, _frm):
    raise _Timeout()


def _worker(task):
    """Compute one circuit's economics honestly. Runs in a child process."""
    name, qasm_path, route, verdict, tw, gov, n_stored, t_stored, source = task
    sys.path.insert(0, APP)
    import economics as EC
    from atlas import safe_parse
    EC.MEAS_N_CAP = OFFLINE_MEAS_N_CAP  # offline: measure, don't estimate (module doc sanctions offline measurement)

    out = {"name": name, "route": route, "n": n_stored, "t_count": t_stored, "source": source}
    try:
        with open(qasm_path) as fh:
            qasm = fh.read()
        n_parsed, circ, warns = safe_parse(qasm)
    except Exception as e:  # noqa: BLE001
        out["error"] = "qasm_parse_failed: %r" % e
        return out

    tractable = ("TRACTABLE" in verdict) and ("INTRACTABLE" not in verdict)  # webui.py logic, verbatim
    escalate = route == "ESCALATE"
    n2q, depth = EC._circuit_factors(circ)
    out.update({"n_parsed": n_parsed, "gates": len(circ), "n2q": n2q, "depth": depth,
                "verdict_class": ("TRACTABLE" if tractable else ("INTRACTABLE" if "INTRACTABLE" in verdict else "WALL")),
                "tractable": tractable})

    # exponent for the module's cost formulas: stored treewidth; where cotengra
    # abstained (null) fall back to the engine's stored governing statevector
    # exponent — a real engine output, never invented.
    if tw is not None:
        tw_eff, exp_src = float(tw), "treewidth(stored)"
    elif gov is not None:
        tw_eff, exp_src = float(gov), "governing_statevector(stored)"
    else:
        tw_eff, exp_src = None, None
    out["exponent_source"] = exp_src

    # --- QPU side (always computable from the parsed circuit + published pricing) ---
    q = EC.qpu_cost(EC.DEFAULT_VENDOR, EPS, n2q, depth, campaign=1)
    out.update({"qpu_usd": q["qpu_cost_eval"], "qpu_shots": q["shots"], "lambda": q["lambda"],
                "gamma_sq": q["gamma_sq"], "mitigation_infeasible": q["mitigation_infeasible"],
                "vendor": EC.DEFAULT_VENDOR, "eps": EPS, "qpu_pricing_src": q["src"]})
    if q["mitigation_infeasible"]:
        out["qpu_usd"] = None
        out["qpu_excluded_reason"] = ("PEC mitigation infeasible: lambda=eps_g*n2q=%.2f exceeds cap %.1f "
                                      "(module reports mitigation_infeasible; no honest $ exists)"
                                      % (q["lambda"], EC.LAMBDA_CAP))

    # --- classical side ---
    if escalate:
        out["classical_usd"] = None
        out["classical_kind"] = None
        out["classical_note"] = "route ESCALATE — beyond classical reach, no classical price exists"
        return out
    if tw_eff is None:
        out["classical_usd"] = None
        out["classical_kind"] = None
        out["classical_excluded_reason"] = "no stored treewidth AND no governing cost — cannot price honestly"
        return out

    old = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(SIM_BUDGET_S)
    try:
        e = EC.economics(n_parsed, circ, tractable, treewidth_log2=tw_eff, eps=EPS,
                         vendor=EC.DEFAULT_VENDOR, campaign=1)
        if tractable:
            # unrounded from the measured seconds (module rounds to 6 dp which floors sub-us costs)
            t_cls = e["classical_sim_s"]
            out["classical_usd"] = (t_cls / 3600.0) * EC.CPU_RATE_HR
            out["classical_sim_s"] = t_cls
            out["classical_measured"] = bool(e["classical_measured"])
            out["classical_kind"] = "measured_mps_sim" if e["classical_measured"] else "estimated_statevector"
            out["classical_engine"] = e["classical_engine"]
        else:
            # module's HPC flops model, unrounded (module rounds to cents)
            out["classical_usd"] = ((2.0 ** tw_eff) / EC.HPC_FLOPS) / 3600.0 * EC.CPU_RATE_HR
            out["classical_usd_module_rounded"] = e["hpc_cost_eval"]
            out["classical_measured"] = False
            out["classical_kind"] = "hpc_flops_model"
            out["classical_engine"] = e["classical_engine"]
    except _Timeout:
        out["classical_usd"] = None
        out["classical_kind"] = None
        out["classical_excluded_reason"] = "measured MPS sim exceeded %ds budget" % SIM_BUDGET_S
    except Exception as ex:  # noqa: BLE001
        out["classical_usd"] = None
        out["classical_kind"] = None
        out["classical_excluded_reason"] = "economics raised: %r" % ex
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)
    return out


def _load_corpus():
    seen, order, dup = {}, [], 0
    for res_path, qasm_dir in BATCHES:
        data = json.load(open(res_path))
        for r in data["results"]:
            nm = r.get("name")
            if nm in seen:
                dup += 1
                continue
            seen[nm] = (r, qasm_dir)
            order.append(nm)
    print("corpus: %d unique circuits (%d duplicate names skipped)" % (len(seen), dup))

    tasks, excluded = [], []
    for nm in order:
        r, qasm_dir = seen[nm]
        qp = os.path.join(qasm_dir, nm + ".qasm")
        if not os.path.exists(qp):
            excluded.append({"name": nm, "route": r.get("route"),
                             "reason": "QASM file not found (%s)" % os.path.relpath(qp, REPO)})
            continue
        gov = r.get("governing_cost_log2")
        if gov is None:
            excluded.append({"name": nm, "route": r.get("route"),
                             "reason": ("no governing classical cost (estimator=%s): x-position cannot be "
                                        "computed honestly; stored union_cost_log2=%s is a magic-fold bound "
                                        "thousands of log2 units off-scale") % (r.get("governing_estimator"),
                                                                                r.get("union_cost_log2"))})
            continue
        tasks.append((nm, qp, r["route"], r["verdict"], r.get("treewidth_log2"), gov,
                      r["n"], r.get("t_count"), r.get("source", "")))
    return seen, tasks, excluded


def _run_tasks(tasks, total=None):
    rows, t0 = [], time.time()
    total = total or len(tasks)
    for i, t in enumerate(tasks):
        row = _worker(t)
        rows.append(row)
        note = row.get("error") or row.get("classical_excluded_reason") or row.get("qpu_excluded_reason") or "ok"
        print("  [%3d/%d] %-30s %s" % (i + 1, total, row["name"], note), flush=True)
    print("computed %d in %.1fs" % (len(tasks), time.time() - t0), flush=True)
    return rows


def compute_shard(shard_idx, shard_n):
    _seen, tasks, _excluded = _load_corpus()
    mine = [t for i, t in enumerate(tasks) if i % shard_n == shard_idx]
    rows = _run_tasks(mine)
    path = os.path.join(HERE, "spend_frontier.shard%d.json" % shard_idx)
    with open(path, "w") as fh:
        json.dump(rows, fh, indent=1)
    print("wrote %s" % path)


def compute(shard_n=0):
    seen, tasks, excluded = _load_corpus()
    if shard_n:
        rows = []
        for i in range(shard_n):
            p = os.path.join(HERE, "spend_frontier.shard%d.json" % i)
            rows.extend(json.load(open(p)))
    else:
        rows = _run_tasks(tasks)

    # attach x + drop hard failures
    by_name = {r["name"]: r for r in rows}
    final = []
    for t in tasks:
        row = by_name[t[0]]
        if row.get("error"):
            excluded.append({"name": row["name"], "route": row["route"], "reason": row["error"]})
            continue
        row["x_log2"] = float(t[5])
        row["union_cost_log2"] = seen[row["name"]][0].get("union_cost_log2")
        final.append(row)

    sys.path.insert(0, APP)
    import economics as EC
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "benchmarks/spend_frontier/generate_spend_frontier.py",
        "pricing_snapshot": {
            "as_of": EC.PRICING_SNAPSHOT_DATE, "region": EC.PRICING_REGION,
            "sources": EC.PRICING_SOURCES, "vendor_default": EC.DEFAULT_VENDOR,
            "per_shot_usd": EC.PER_SHOT_VENDORS[EC.DEFAULT_VENDOR]["per_shot_usd"],
            "task_usd": EC.PER_SHOT_VENDORS[EC.DEFAULT_VENDOR]["task_usd"],
            "task_floor_usd": EC.PER_SHOT_VENDORS[EC.DEFAULT_VENDOR]["task_floor_usd"],
            "eps_g_2q": EC.EPS_G_BY_VENDOR[EC.DEFAULT_VENDOR],
            "cpu_rate_usd_hr": EC.CPU_RATE_HR, "hpc_flops_per_s": EC.HPC_FLOPS,
        },
        "assumptions": [
            "eps=1e-2 (casual precision, module/webui default); shots N = ceil(1/eps^2) * e^(4*eps_g*n2q) (PEC, Quek/Eisert arXiv:2210.11505), floor 2500 (IonQ)",
            "QPU $ = per-eval: max(task_fee + N*per_shot, task_floor) on AWS Braket IonQ Forte published rates (economics.py PRICING_SNAPSHOT_DATE)",
            "n2q = two-qubit gates (cx/cnot/cz) of the circuit AFTER the engine's own safe_parse decomposition (same as the live verdict)",
            "classical $ for TRACTABLE circuits = MEASURED quimb CircuitMPS(max_bond=256) wall-time on this machine x $0.10/hr CPU; measured offline, MEAS_N_CAP lifted per the module's own offline-measurement note",
            "classical $ for WALL (non-tractable, classical-tier) circuits = economics.py HPC flops model: 2^exponent / 1e13 flops/s (~1x A100) x $0.10/hr; exponent = stored treewidth, or the stored governing statevector exponent where cotengra abstained (exponent_source per row)",
            "ESCALATE circuits have NO classical price by definition of the route — only the QPU marker exists",
            "QPU $ is a counterfactual: spend avoided by not mis-routing, not a realized saving; not financial advice",
            "mitigation_infeasible circuits (lambda > 12.5) have no honest QPU price and are excluded from the QPU layer",
        ],
        "palette": PALETTE,
        "counts": {"corpus_unique": len(seen), "plotted": len(final), "excluded": len(excluded)},
        "rows": final,
        "excluded": excluded,
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(payload, fh, indent=1)
    print("wrote %s (%d rows, %d excluded)" % (OUT_JSON, len(final), len(excluded)))
    return payload


# ============================================================================
# SVG rendering
# ============================================================================
def _fmt_usd(v):
    if v is None:
        return "n/a"
    if v >= 1000:
        return "$%s" % ("{:,.0f}".format(v))
    if v >= 1:
        return "$%.2f" % v
    if v >= 0.001:
        return "$%.3f" % v
    return "$%.1e" % v


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render(payload, w=1120, h=640, compact=False):
    rows = payload["rows"]
    snap = payload["pricing_snapshot"]["as_of"]
    ml, mr, mt, mb = (58, 20, 74, 52) if compact else (74, 26, 108, 66)
    pw, ph = w - ml - mr, h - mt - mb

    xmax = 132.0
    ymin_e, ymax_e = -9, 5          # $1e-9 .. $100k, log10
    X = lambda x: ml + (min(x, xmax) / xmax) * pw
    Y = lambda usd: mt + ph - ((math.log10(usd) - ymin_e) / (ymax_e - ymin_e)) * ph

    def yc(usd):  # clamp into the plotted domain; flag which edge
        lo, hi = 10.0 ** ymin_e, 10.0 ** ymax_e
        edge = "top" if usd > hi else ("bottom" if usd < lo else None)
        return Y(min(max(usd, lo), hi)), edge

    s = []
    s.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" font-family="Helvetica,Arial,sans-serif">' % (w, h))
    s.append('<rect width="%d" height="%d" fill="%s"/>' % (w, h, SURFACE))

    # title / subtitle / footer
    if compact:
        s.append('<text x="%d" y="26" fill="%s" font-size="14" font-weight="700">The Spend Frontier — classical $ vs QPU $ per circuit</text>' % (ml, INK))
        s.append('<text x="%d" y="43" fill="%s" font-size="9.5">%d circuits · real engine routes · published pricing %s · QPU $ = spend avoided by not mis-routing · not financial advice</text>'
                 % (ml, INK2, len(rows), snap))
    else:
        s.append('<text x="%d" y="34" fill="%s" font-size="19" font-weight="700">The Spend Frontier — what each circuit costs to run, classically vs on a QPU</text>' % (ml, INK))
        s.append('<text x="%d" y="56" fill="%s" font-size="11.5">115 published/community circuits (%d plotted, %d unpriceable excluded — logged) · real engine routes · published pricing snapshot %s</text>'
                 % (ml, INK2, len(rows), payload.get("counts", {}).get("excluded", 115 - len(rows)), snap))
        s.append('<text x="%d" y="72" fill="%s" font-size="11.5">counterfactual: QPU $ = spend avoided by not mis-routing, not a realized saving · not financial advice</text>' % (ml, INK2))
    s.append('<text x="%d" y="%d" fill="%s" font-size="%s">atlas.krenniq.com · reproducible: benchmarks/spend_frontier/</text>'
             % (ml, h - 12, INK3, "8.5" if compact else "10"))

    # frontier region: engine escalates at treewidth > 50 (classical_frontier, economics.py)
    fx = X(50)
    s.append('<rect x="%.1f" y="%d" width="%.1f" height="%d" fill="#ae316e" opacity="0.05"/>' % (fx, mt, ml + pw - fx, ph))
    s.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1" stroke-dasharray="3 4" opacity="0.45"/>' % (fx, mt, fx, mt + ph, INK3))

    # gridlines + y ticks
    for e in range(ymin_e, ymax_e + 1):
        yy = Y(10.0 ** e)
        major = e % 3 == 2 or e in (ymin_e, ymax_e)
        s.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1" opacity="%s"/>'
                 % (ml, yy, ml + pw, yy, GRID, "1" if major else "0.55"))
        lab = {5: "$100k", 4: "$10k", 3: "$1k", 2: "$100", 1: "$10", 0: "$1", -1: "10¢", -2: "1¢",
               -3: "$10⁻³", -4: "$10⁻⁴", -5: "$10⁻⁵", -6: "$10⁻⁶", -7: "$10⁻⁷", -8: "$10⁻⁸", -9: "$10⁻⁹"}[e]
        if (not compact) or e % 3 == 2 or e == 0:
            s.append('<text x="%d" y="%.1f" fill="%s" font-size="%s" text-anchor="end">%s</text>'
                     % (ml - 7, yy + 3, INK2, "8.5" if compact else "10", lab))
    # x ticks
    for xv in range(0, 121, 20):
        xx = X(xv)
        s.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1"/>' % (xx, mt + ph, xx, mt + ph + 4, INK3))
        s.append('<text x="%.1f" y="%d" fill="%s" font-size="%s" text-anchor="middle">2^%d</text>'
                 % (xx, mt + ph + 15, INK2, "8.5" if compact else "10", xv))
    s.append('<text x="%.1f" y="%d" fill="%s" font-size="%s" text-anchor="middle">measured classical hardness — engine governing cost (log₂ units)</text>'
             % (ml + pw / 2, mt + ph + (28 if compact else 33), INK2, "9" if compact else "11"))
    s.append('<text x="%d" y="%.1f" fill="%s" font-size="%s" text-anchor="middle" transform="rotate(-90 %d %.1f)">$ per evaluation (log)</text>'
             % (16 if compact else 20, mt + ph / 2, INK2, "9" if compact else "11", 16 if compact else 20, mt + ph / 2))

    # region captions — in the empty band between classical dots and QPU marks (ink tokens, never series colors)
    ycap = Y(1.0) + 4          # $1 line: the vertical gap between the two cost clouds
    s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="%s" font-style="italic">classical route is cheaper — spend you avoid</text>'
             % (ml + 8, ycap, INK2, "9" if compact else "11"))
    s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="%s" font-style="italic" text-anchor="end">beyond classical reach —</text>'
             % (ml + pw - 8, ycap, INK2, "9" if compact else "11"))
    s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="%s" font-style="italic" text-anchor="end">QPU is the only option</text>'
             % (ml + pw - 8, ycap + 14, INK2, "9" if compact else "11"))
    if not compact:
        s.append('<text x="%d" y="%d" fill="%s" font-size="9" text-anchor="end">bottom-edge points: module cost &lt; $10⁻⁹/eval (clamped) · ▲ = QPU off-scale &gt;$100k (real $ in hover) · QPU marks: IonQ Forte per-eval, eps=10⁻²</text>'
                 % (ml + pw, h - 12, INK3))

    # marks
    r_cls = 3.2 if compact else 4.5
    r_qpu = 2.4 if compact else 3.2
    pts = {}   # name -> (x, y_cls, y_qpu) for labels
    marks = []
    for row in sorted(rows, key=lambda r: ROUTE_ORDER.index(r["route"])):
        x = X(row["x_log2"])
        tt = "%s (n=%d, route %s) — classical: %s · QPU (%s, eps=%s): %s" % (
            row["name"], row["n"], row["route"],
            _fmt_usd(row.get("classical_usd")) + (" [" + (row.get("classical_kind") or "") + "]" if row.get("classical_usd") is not None else
                                                  (" (" + (row.get("classical_note") or row.get("classical_excluded_reason") or "") + ")")),
            row["vendor"], row["eps"],
            _fmt_usd(row.get("qpu_usd")) if row.get("qpu_usd") is not None else "infeasible (mitigation overhead exceeds cap)")
        tt = _esc(tt)
        ycl = yq = None
        if row.get("qpu_usd") is not None:
            yq, edge = yc(row["qpu_usd"])
            if edge == "top":   # off-scale: explicit up-arrow at the top edge, real $ in the tooltip
                marks.append('<path d="M %.1f %.1f l 4 7 l -8 0 z" fill="none" stroke="%s" stroke-width="1.3" opacity="0.9"><title>%s</title></path>'
                             % (x, yq + 1, QPU_GRAY, tt))
            elif row["route"] == "ESCALATE":
                marks.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" stroke-width="1.8"><title>%s</title></circle>'
                             % (x, yq, r_cls - 0.6, PALETTE["ESCALATE"], tt))
            else:
                marks.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="none" stroke="%s" stroke-width="1.3" opacity="0.85"><title>%s</title></circle>'
                             % (x, yq, r_qpu, QPU_GRAY, tt))
        if row.get("classical_usd") is not None:
            ycl, _edge = yc(row["classical_usd"])
            marks.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="%s" stroke-width="1.6"><title>%s</title></circle>'
                         % (x, ycl, r_cls, PALETTE[row["route"]], SURFACE, tt))
        pts[row["name"]] = (x, ycl, yq, row)

    s.extend(marks)

    # ---- legend: one horizontal row above the plot (right-aligned, never over data) ----
    fs = 8.5 if compact else 10.5
    leg = [("CPU", "CPU", "dot"), ("TENSOR", "TENSOR", "dot"), ("HPC_FIRST", "HPC_FIRST", "dot"),
           ("ESCALATE", "ESCALATE (QPU only)", "ring"), (QPU_GRAY, "QPU alternative (same circuit)", "hollow")]
    gap_sw, gap_item = 8, 16
    widths = [gap_sw + len(lab) * fs * 0.58 for _k, lab, _m in leg]
    lx = ml + pw - (sum(widths) + gap_item * (len(leg) - 1))
    ly = mt - (10 if compact else 14)
    for (k, lab, mk), wd in zip(leg, widths):
        col = PALETTE.get(k, k)
        if mk == "dot":
            s.append('<circle cx="%.1f" cy="%.1f" r="4" fill="%s"/>' % (lx, ly, col))
        elif mk == "ring":
            s.append('<circle cx="%.1f" cy="%.1f" r="3.6" fill="none" stroke="%s" stroke-width="1.8"/>' % (lx, ly, col))
        else:
            s.append('<circle cx="%.1f" cy="%.1f" r="3" fill="none" stroke="%s" stroke-width="1.3"/>' % (lx, ly, col))
        s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="%s">%s</text>' % (lx + gap_sw, ly + 3.2, INK, fs, lab))
        lx += wd + gap_item

    # ---- selective direct labels with leader lines ----
    def label(name, use, text, dx, dy, anchor="start"):
        p = pts.get(name)
        if not p:
            return
        x, ycl, yq, _row = p
        yy = ycl if use == "cls" else yq
        if yy is None:
            return
        tx, ty = x + dx, yy + dy
        s.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="0.8" opacity="0.7"/>'
                 % (x + (2 if dx > 0 else -2), yy - (2 if dy < 0 else -2) if abs(dy) > 4 else yy, tx - (4 if anchor == "start" else -4), ty - 3.5, INK3))
        for j, line in enumerate(text.split("\n")):
            s.append('<text x="%.1f" y="%.1f" fill="%s" font-size="%s" text-anchor="%s">%s</text>'
                     % (tx, ty + j * 11.5, INK2, "8.5" if compact else "10", anchor, _esc(line)))

    lbl = payload.get("_labels", {})
    if not compact:
        m45 = pts.get("multiplier_n45")
        if m45:
            cusd = m45[3].get("classical_usd")
            label("multiplier_n45", "cls", "multiplier_n45 — #T=2,646 → CPU %s" % ("<$0.01" if cusd is not None and cusd < 0.01 else _fmt_usd(cusd)), 38, -96)
        label("sycamore_rcs_53q_depth20", "qpu", "sycamore_rcs_53q_depth20\nQPU-only · %s/eval" % lbl.get("syc20", ""), -12, -30, anchor="end")
        label("kicked_ising_127q_hard_5steps", "qpu", "kicked_ising_127q_hard_5steps\nQPU-only · %s/eval" % lbl.get("ki5", ""), -14, 34, anchor="end")
        if lbl.get("c805_name"):
            label(lbl["c805_name"], "qpu", "%s\n%s/eval on QPU — spend avoided" % (lbl["c805_name"], lbl.get("c805_usd", "")), 44, 44)
    else:
        label("multiplier_n45", "cls", "multiplier_n45: CPU <$0.01", 26, -42)
        label("sycamore_rcs_53q_depth20", "qpu", "sycamore 53q d20: QPU-only", -10, -14, anchor="end")

    s.append("</svg>")
    return "\n".join(s)


def render_all(payload):
    rows = payload["rows"]
    # find the $805-class example: CPU-route circuit with QPU cost closest to $805 in [790, 830]
    best = None
    for r in rows:
        q = r.get("qpu_usd")
        if r["route"] == "CPU" and q is not None and 790 <= q <= 830:
            if best is None or abs(q - 805) < abs(best[1] - 805):
                best = (r["name"], q)
    lbl = {}
    if best:
        lbl["c805_name"], lbl["c805_usd"] = best[0], _fmt_usd(best[1])
    for r in rows:
        if r["name"] == "sycamore_rcs_53q_depth20" and r.get("qpu_usd") is not None:
            lbl["syc20"] = _fmt_usd(r["qpu_usd"])
        if r["name"] == "kicked_ising_127q_hard_5steps" and r.get("qpu_usd") is not None:
            lbl["ki5"] = _fmt_usd(r["qpu_usd"])
    payload["_labels"] = lbl

    full = render(payload, 1120, 640, compact=False)
    comp = render(payload, 720, 360, compact=True)
    outs = [(os.path.join(HERE, "atlas-spend-frontier.svg"), full),
            (os.path.join(HERE, "atlas-spend-frontier-compact.svg"), comp),
            (os.path.join(SITE, "atlas-spend-frontier.svg"), full),
            (os.path.join(SITE, "atlas-spend-frontier-compact.svg"), comp)]
    for path, content in outs:
        with open(path, "w") as fh:
            fh.write(content)
        print("wrote %s" % path)


def main():
    if "--shard" in sys.argv:
        spec = sys.argv[sys.argv.index("--shard") + 1]
        i, n = (int(v) for v in spec.split("/"))
        compute_shard(i, n)
        return
    if "--render-only" in sys.argv:
        payload = json.load(open(OUT_JSON))
    elif "--merge" in sys.argv:
        payload = compute(shard_n=int(sys.argv[sys.argv.index("--merge") + 1]))
    else:
        payload = compute()
    render_all(payload)


if __name__ == "__main__":
    main()

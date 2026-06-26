"""webui.py -- interfaz IDE del atlas (stdlib http.server, sin dependencias extra). Envuelve atlas.py.

Lanzar:   cd physics-magnitude-lab && PYTHONPATH=src pixi run python <ruta>/webui.py
Abrir:    http://localhost:8791

IDE de 3 zonas: topbar + sidebar (diagrama de fases interactivo + metricas) + editor con tabs.
KILLER: (1) clic en el diagrama -> GENERA un circuito en ese punto.  (2) analisis as-you-type con ESTELA.
Metricas validadas: magia vs Stim, MPS vs quimb, treewidth vs cotengra.
"""
from __future__ import annotations
import sys, os, json, threading, hashlib
sys.path.insert(0, "src")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from atlas import (cost_atlas, build_target, decompose, to_qasm, _verify_hop, _demo_qasm, safe_parse,
                   validate_n, which_flattener)   # which_flattener: graceful (motor opcional)
try:
    import physics_invariants as _phys                       # F-1: invariante FISICO analitico (entropia)
    _PHYS_SELFTEST = _phys.selftest()                        # se calcula una vez al arrancar
except Exception:
    _phys = None; _PHYS_SELFTEST = None
try:
    import anthropic as _anthropic                           # Fase 6: chat REAL (Claude API), opcional
except Exception:
    _anthropic = None                                        # sin SDK -> /api/chat responde fallback honesto
try:
    from atlas_certificate import certificate as _certificate  # capa de certificado honesto (witness+conformal+driver+impossibility)
except Exception:
    _certificate = None                                       # sin la capa -> diagnose sigue igual, sin certificado
try:
    from boundary_sweep import harden as _harden              # explorar complejidad / variante mas dura
except Exception:
    _harden = None
try:
    from atlas_segment import segment_triage as _segment      # triage hibrido por segmento (donde vive la dureza)
except Exception:
    _segment = None
try:
    from atlas_gpu_route import gpu_route_advice as _gpu_advice  # ruta GPU statevector (frontera dinamica)
except Exception:
    _gpu_advice = None
try:
    from atlas_variational import variational_triage as _variational  # triage VQE/QAOA (caso QPU real)
except Exception:
    _variational = None
try:
    from atlas_benchmark_bundle import bundle as _bench_bundle        # benchmark auditable (corpus+confusion+CI)
except Exception:
    _bench_bundle = None

PORT = int(os.environ.get("ATLAS_PORT", "8791"))
HOST = os.environ.get("ATLAS_HOST", "127.0.0.1")   # 0.0.0.0 para deploy (HF Space / Docker)
_HARDEN_JOBS = {}; _HARDEN_LOCK = threading.Lock(); _HARDEN_SEQ = [0]   # async job store p/ /api/harden

PAGE = r"""<!doctype html><html lang=es><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Atlas - dureza cuantica</title>
<link rel=preconnect href=https://fonts.googleapis.com><link rel=preconnect href=https://fonts.gstatic.com crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel=stylesheet><style>
/* TEMA: paleta del objeto 3D flotante (oro #f5a623 · naranja #ff5722 · cyan #00e5ff · magenta
   #e61062) sobre superficies TRANSLÚCIDAS (frosted glass) para que el objeto se vea volando detrás. */
:root{--bg:#07070b;--surface:rgba(20,18,30,.52);--surface2:rgba(34,28,48,.60);--border:rgba(0,229,255,.18);--accent:#f5a623;--accent2:#ffb74d;
--text:#eef2f7;--text2:#9aa6b8;--text3:#6b7689;
/* alias retro-compat remapeados a la paleta del objeto + translúcido */
--p1:rgba(20,18,30,.52);--p2:rgba(34,28,48,.60);--bd:rgba(0,229,255,.18);--tp:#eef2f7;--ts:#9aa6b8;--th:#6b7689;
--vio:#e61062;--vio2:#ff5c8a;--blue:#00e5ff;--teal:#00e5ff;--green:#34d399;--red:#ff5722;--warn:#f5a623}
/* frosted glass: las superficies translúcidas se leen bien sobre el objeto en movimiento */
.topbar,.mcard,.tool,.worksum,.outbody,#certPanel,.landscape-card,.noise-box,.why-card,.recommend .rec-card,.score-tree,.demo-box{backdrop-filter:blur(9px) saturate(1.15);-webkit-backdrop-filter:blur(9px) saturate(1.15)}
/* B9 scrollbars finas */
::-webkit-scrollbar{width:5px;height:5px}::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}::-webkit-scrollbar-thumb:hover{background:var(--text3)}
*{box-sizing:border-box;margin:0}html,body{height:100%}body{background:var(--bg);color:var(--tp);
font:400 13px/1.5 'IBM Plex Sans',system-ui,sans-serif;overflow:hidden}
.topbar{height:48px;display:flex;align-items:center;gap:18px;padding:0 18px;background:var(--surface);border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:9px;font-weight:600;font-size:14px}
.claim{color:var(--text3);font-size:12px;border-left:1px solid var(--border);padding-left:12px;max-width:520px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.logo-net{--logo-size:28px;width:var(--logo-size);height:var(--logo-size);display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto}
.logo-net svg{width:100%;height:100%;display:block;overflow:visible}.logo-net .shell{fill:rgba(99,102,241,.08);stroke:rgba(148,163,184,.28);stroke-width:.8}.logo-net .edge{fill:none;stroke-linecap:round;vector-effect:non-scaling-stroke}.logo-net .edge.cyan{stroke:#00e5ff;stroke-width:1.4;opacity:.78}.logo-net .edge.mag{stroke:#e61062;stroke-width:1.8;opacity:.9}.logo-net .edge.thin{stroke:#00e5ff;stroke-width:.65;opacity:.28}.logo-net .node{stroke:#05060a;stroke-width:.9;filter:drop-shadow(0 0 3px rgba(245,166,35,.55))}.logo-net .node.gold{fill:#f5a623}.logo-net .node.hot{fill:#ff5722}.logo-net .core-glow{fill:url(#atlasLogoGlow);opacity:.65}
.top-logo{--logo-size:27px}.dp-logo-net{--logo-size:32px}
.brand .dim{color:var(--th);font-weight:400}
.tabs{display:flex;gap:4px}.tab{background:transparent;border:0;color:var(--ts);padding:6px 14px;border-radius:7px;
cursor:pointer;font:500 13px 'IBM Plex Sans';display:flex;align-items:center;gap:7px}
.tab.active{background:var(--p2);color:var(--tp)}.tab .dot{width:7px;height:7px;border-radius:50%;background:var(--th)}
.tab.active .dot{background:var(--green);box-shadow:0 0 8px var(--green)}
.sp{flex:1}.badges{display:flex;gap:8px}.badge{background:var(--p2);border:1px solid var(--bd);color:var(--ts);
font:500 11px 'JetBrains Mono';padding:4px 9px;border-radius:6px}.badge.v{color:var(--vio2);border-color:#3b2d63}
.app{display:flex;height:calc(100% - 84px)}   /* topbar 48 + modebar 36 */
.side{width:392px;background:linear-gradient(180deg,#10121b,#0b0b10);border-left:1px solid var(--bd);overflow-y:auto;padding:14px;flex-shrink:0;order:2}   /* columna derecha exacta: acciones + decision */
.right-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}.right-act{border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.025);color:#cbd5e1;border-radius:999px;padding:8px 10px;font:750 11px 'IBM Plex Sans';letter-spacing:.02em;text-align:center}.right-act.good{color:#34d399}.right-cost{grid-column:1/3;border-color:rgba(99,102,241,.24);color:#a5b4fc;text-transform:uppercase;letter-spacing:.12em}
.sech{font:600 12px 'IBM Plex Sans';letter-spacing:.08em;text-transform:uppercase;color:var(--text3);margin:18px 0 10px}
.sech:first-child{margin-top:0}
#phase{width:100%;border:1px solid var(--bd);border-radius:8px;background:#0a0a0e;cursor:crosshair;display:block}
.ph-dot{cursor:pointer;opacity:.82;transition:opacity .12s}
.ph-dot:hover{opacity:1;stroke:#fff;stroke-width:1.5}
.phint{font-size:11px;color:var(--th);margin-top:6px;text-align:center}
.mcard{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:var(--surface);
border:1px solid var(--border);border-radius:8px;margin-bottom:7px;transition:.2s}
.mcard.hl{border-color:#22C55E;background:rgba(34,197,94,.07);box-shadow:0 0 0 1px rgba(34,197,94,.3)}   /* "gobernó" en verde (jerarquía v2) */
.mcard .l{display:flex;align-items:center;gap:9px;color:var(--text3);font-size:11px;text-transform:uppercase;letter-spacing:.05em}
.mcard .l .d{width:8px;height:8px;border-radius:50%}.mcard .val{font:800 22px 'JetBrains Mono';color:#fff}   /* número protagonista (spec §5.2) */
.refs a{display:block;color:var(--ts);text-decoration:none;font-size:12px;padding:6px 0;border-bottom:1px solid var(--bd)}
.refs a:hover{color:var(--vio2)}.refs a::after{content:' \2197';color:var(--th)}
.main{flex:1;display:flex;flex-direction:column;min-width:0;order:1}   /* area de trabajo a la IZQUIERDA */
.mhead{height:46px;display:flex;align-items:center;gap:12px;padding:0 16px;background:var(--p1);border-bottom:1px solid var(--bd)}
.fname{font:500 13px 'JetBrains Mono';color:var(--ts)}.mhead .sp{flex:1}
.tool{background:transparent;border:0;color:var(--ts);cursor:pointer;font:500 12px 'IBM Plex Sans';padding:6px 10px;border-radius:6px}
.tool:hover{background:var(--p2);color:var(--tp)}.hero{background:linear-gradient(135deg,var(--vio),#6366f1);color:#fff;padding:7px 16px}
.hero:hover{filter:brightness(1.1)}
.edwrap{flex:1 1 38%;display:flex;overflow:hidden;position:relative;min-height:0;min-width:240px}  /* Bug#6: el editor no se aplasta cuando paneles (cert/segment) se expanden */
.main.gen-mode .edwrap{flex-basis:70%}.main.gen-mode .worksum{width:30%}
.lines{padding:14px 8px 14px 14px;text-align:right;color:var(--th);font:400 13px/1.6 'JetBrains Mono';
background:var(--p1);user-select:none;overflow:hidden;white-space:pre}
/* editor con syntax highlight (overlay): textarea texto transparente sobre capa coloreada #qasm-hl */
.ed-area{flex:1;position:relative;overflow:hidden;min-width:0}
#qasm,#qasm-hl{position:absolute;inset:0;margin:0;border:0;padding:14px;font:400 13px/1.6 'JetBrains Mono';
  white-space:pre-wrap;overflow-wrap:break-word;word-break:break-word;tab-size:2}
#qasm-hl{background:var(--bg);color:var(--tp);overflow:auto;pointer-events:none;z-index:0}
#qasm{background:transparent;color:transparent;resize:none;outline:none;caret-color:var(--vio2);overflow:auto;z-index:1}
#qasm::selection{background:#3b2d63}
.hl-dir{color:#8B5CF6}.hl-cliff{color:#6366F1}.hl-magic{color:#F59E0B}.hl-meas{color:#10B981}.hl-com{color:#6B7280}
.genpanel{flex:1;padding:18px;overflow-y:auto;display:none}.genpanel.on{display:block}
.gen-controls{min-width:0;display:grid;grid-template-columns:1fr 1fr;gap:14px 18px;align-content:start}.gen-explorer-slot{min-width:0}
.gctrl{margin-bottom:0;max-width:none}.gctrl label{display:block;color:var(--ts);font-size:12px;margin-bottom:7px}
/* V2-6: generador 2-col + PASO 1 + ejemplos rápidos */
.gen-head{grid-column:1/-1;display:flex;align-items:center;gap:8px;margin-bottom:2px}
.gen-head-t{font:700 12px 'IBM Plex Sans';color:var(--text2);text-transform:uppercase;letter-spacing:.06em}
.paso-badge{padding:2px 8px;border-radius:20px;background:rgba(99,102,241,.2);color:var(--accent2);font:700 10px 'IBM Plex Sans';letter-spacing:.04em}
.gen-actions{grid-column:1/-1;display:flex;gap:8px;align-items:center;margin-top:4px}
.gen-ex{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:4px;border-top:1px solid var(--bd);padding-top:10px}
.gen-ex-lbl{flex-basis:100%;font:600 9.5px 'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.06em;color:var(--text3);margin-bottom:1px}
.gen-ex-btn{background:var(--surface2);border:1px solid var(--bd);color:var(--text2);border-radius:6px;padding:5px 10px;font:500 11px 'IBM Plex Sans';cursor:pointer}
.gen-ex-btn:hover{border-color:var(--accent);color:#e2e8f0}
@media(max-width:980px){.gen-controls{grid-template-columns:1fr}}
/* V2-7: barra de benchmark medido (framing honesto) */
.bench-bar{margin-top:8px;padding:8px 10px;border:1px solid rgba(52,211,153,.22);background:rgba(52,211,153,.05);border-radius:8px}
.bench-k{font:700 9px 'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.08em;color:var(--green);display:block;margin-bottom:2px}
.bench-v{font:10.5px 'IBM Plex Sans';color:var(--text2)}.bench-v b{color:#e2e8f0}
.bench-track{height:3px;border-radius:2px;background:var(--surface2);margin-top:6px;overflow:hidden}
.bench-fill{height:100%;width:99.1%;background:linear-gradient(90deg,var(--green),var(--accent))}
.seg{display:flex;gap:0;border:1px solid var(--bd);border-radius:8px;overflow:hidden;width:fit-content}
.seg button{background:transparent;border:0;color:var(--ts);padding:9px 22px;cursor:pointer;font:500 13px 'IBM Plex Sans'}
.seg button.on{background:var(--vio);color:#fff}
.gn{width:120px;background:var(--p2);border:1px solid var(--bd);color:var(--tp);padding:10px;border-radius:8px;
font:500 14px 'JetBrains Mono';text-align:center}
.outhead{display:flex;gap:2px;background:var(--p1);border-top:1px solid var(--bd);padding:0 12px}
.otab{background:transparent;border:0;color:var(--ts);padding:11px 14px;cursor:pointer;font:500 12px 'IBM Plex Sans';
border-bottom:2px solid transparent;display:flex;align-items:center;gap:6px}
.otab.active{color:var(--tp);border-color:var(--vio)}.otab .bdg{width:6px;height:6px;border-radius:50%;background:var(--vio)}
.outbody{flex:1 1 0;min-height:240px;overflow:auto;padding:16px;background:var(--p1);border-top:1px solid var(--bd);display:grid;grid-template-columns:1fr 1fr;gap:14px}
/* layout segun mockup: editor (izq) + resumen (der) arriba; tabs + circuito full-width abajo */
.worktop{display:flex;flex-wrap:wrap;flex:1.05 1 0;min-height:150px;overflow:auto}  /* Bug#6/#2: wrap en vez de aplastar · reproductor (outbody) con mas espacio */
#certPanel{min-width:300px;max-width:560px;flex:1 1 320px;overflow:auto}            /* Bug#6: cert acotado, no domina el ancho */
.worksum{width:62%;flex-shrink:0;overflow-y:auto;padding:14px 16px;background:var(--p1);border-left:1px solid var(--bd)}
.opane{display:none}.opane.on{display:block}.outbody>#pResultado,.outbody>#pLog{display:block}.outbody>#pCircuito,.outbody>#pQASM{display:none}
.diag-grid{display:grid;grid-template-columns:minmax(292px,1fr) minmax(292px,.94fr);gap:12px;align-items:start}
.diag-primary{min-width:0}.diag-explorer{min-width:0}.diag-explorer .landscape-card{position:sticky;top:0;margin-bottom:0}
.diag-explorer .landscape-grid{grid-template-columns:1fr}.diag-explorer .landscape-side{margin-top:8px}.diag-explorer .landscape-card #phase{min-height:190px}.diag-explorer .landscape-card .cube3d{height:186px}
.chips{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}.chip{font:600 12px 'IBM Plex Sans';padding:4px 10px;border-radius:6px}
.chip.win{border-width:1.5px !important;box-shadow:0 0 8px -2px currentColor}
.chip b{font-family:'JetBrains Mono'}.c-magic{background:#2a1a52;color:var(--vio2)}.c-libro{background:#0a3d3a;color:var(--teal)}
.c-mps{background:#13294d;color:#60a5fa}.c-spread{background:#0e3a2a;color:#34d399}.c-tw{background:var(--p2);color:var(--ts)}
.verd{padding:14px 16px;background:rgba(52,211,153,0.08);border-left:4px solid var(--green);border-radius:0 8px 8px 0;display:flex;align-items:center;gap:12px}
.noise-box{margin-top:10px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 12px}
.noise-head{display:flex;align-items:center;gap:10px;font-size:13px;font-weight:600;color:var(--text2);margin-bottom:8px}
.noise-head .nchev{cursor:pointer;color:var(--text3);transition:transform .2s;font-size:11px}
.noise-box.collapsed .noise-out{display:none}.noise-box.collapsed .nchev{transform:rotate(-90deg)}
.noise-head input[type=range]{flex:1;accent-color:#fbbf24;height:4px}
.noise-pl{font-family:'JetBrains Mono';color:#e8e8ee;min-width:46px;text-align:right;text-transform:none;letter-spacing:0}
.noise-out{font:400 12px/1.7 'JetBrains Mono';color:#a0a0ad}
.circ-head{margin:12px 0 6px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#64748b;display:flex;align-items:center;gap:10px}
.playbtn{background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;border:none;border-radius:5px;padding:3px 10px;font-size:10px;font-weight:700;letter-spacing:.04em;cursor:pointer;text-transform:none}
.playbtn:hover{opacity:.88}
.loopl{display:inline-flex;align-items:center;gap:3px;font:600 10px 'JetBrains Mono';color:#94a3b8;text-transform:none;letter-spacing:0}
.loopl input{width:38px;background:#0f1628;color:#e2e8f0;border:1px solid #2a2a36;border-radius:4px;padding:2px 4px;font-family:'JetBrains Mono';font-size:10px}
#loopsec{color:#64748b}
#circ-inline{max-height:320px;overflow:auto}
.verd.w{border-color:var(--red);background:rgba(248,113,113,0.08)}
.verd .ico{flex-shrink:0;width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:700;background:var(--green);color:#0c0c10}
.verd.w .ico{background:var(--red)}
.verd .tx{font-weight:600;font-size:14px;color:var(--text);line-height:1.4}.verd.w .tx{color:var(--text)}
.warn{margin-top:10px;color:var(--warn);font-size:12px}.warn b{font-family:'JetBrains Mono'}
.answer-card{background:linear-gradient(180deg,rgba(255,255,255,.045),rgba(255,255,255,.018));border:1px solid rgba(255,255,255,.09);border-radius:12px;padding:20px;margin-bottom:12px}
/* jerarquía v2 aplicada a v1: borde+glow por RUTA (verdict colors del spec) */
.answer-card[data-route=cpu]{border-color:#22C55E;box-shadow:0 0 16px rgba(34,197,94,.12);background:rgba(34,197,94,.06)}
.answer-card[data-route=tensor]{border-color:#3B82F6;box-shadow:0 0 16px rgba(59,130,246,.12);background:rgba(59,130,246,.06)}
.answer-card[data-route=hpcfirst]{border-color:#F97316;box-shadow:0 0 16px rgba(249,115,22,.12);background:rgba(249,115,22,.06)}
.answer-card[data-route=escalate]{border-color:#8B5CF6;box-shadow:0 0 16px rgba(139,92,246,.12);background:rgba(139,92,246,.06)}
.answer-card .answer-title{font-size:19px}   /* headline más protagonista (spec §5.1) */
.answer-q{font-size:11px;color:var(--text3);font-weight:700;text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px}
.answer-main{display:flex;align-items:flex-start;gap:14px;margin-bottom:12px}.answer-badge{min-width:78px;text-align:center;border-radius:8px;padding:8px 10px;font:800 23px 'IBM Plex Sans';letter-spacing:.02em}.answer-badge.yes{background:rgba(16,185,129,.14);color:#34d399;border:1px solid rgba(16,185,129,.35)}.answer-badge.no{background:rgba(239,68,68,.13);color:#f87171;border:1px solid rgba(239,68,68,.35)}.answer-badge.maybe{background:rgba(245,158,11,.13);color:#fbbf24;border:1px solid rgba(245,158,11,.35)}
.answer-title{font-size:17px;font-weight:750;color:var(--text);line-height:1.25}.answer-sub{font-size:12px;color:var(--text2);margin-top:4px;line-height:1.45}
.score-row{display:grid;grid-template-columns:112px 1fr 68px;align-items:center;gap:10px;margin:10px 0 12px}.score-label{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.08em}.score-track{height:9px;border-radius:999px;background:linear-gradient(90deg,#34d399 0%,#fbbf24 48%,#f87171 100%);position:relative;overflow:hidden}.score-pin{position:absolute;top:-4px;width:3px;height:17px;background:#fff;border-radius:3px;box-shadow:0 0 10px rgba(255,255,255,.55)}.score-num{font:800 18px 'JetBrains Mono';color:var(--text)}
.score-scale{display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin:-5px 0 12px;padding-left:122px}.score-scale span{font-size:9px;color:var(--text3);text-align:center;border-top:1px solid rgba(255,255,255,.08);padding-top:3px}
.score-tree{margin:8px 0 12px;padding:9px 10px;border:1px solid rgba(255,255,255,.08);border-radius:8px;background:rgba(255,255,255,.025);font:11px 'JetBrains Mono';color:#94a3b8}.score-tree .root{color:#e5e7eb;font-weight:800;margin-bottom:4px}.score-tree .leaf{display:flex;justify-content:space-between;border-top:1px solid rgba(255,255,255,.045);padding-top:4px;margin-top:4px}.score-tree b{color:#cbd5e1}
.history-list{display:flex;flex-direction:column;gap:6px}.hist-item{border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:7px 8px;background:rgba(255,255,255,.025);cursor:pointer}.hist-item:hover{border-color:rgba(99,102,241,.45)}.hist-top{display:flex;justify-content:space-between;gap:8px;font:800 10px 'JetBrains Mono';color:#e5e7eb}.hist-sub{font-size:9px;color:#64748b;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.hist-empty{font-size:10px;color:#64748b;line-height:1.4}
.answer-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.answer-kv{background:rgba(0,0,0,.18);border:1px solid rgba(255,255,255,.06);border-radius:7px;padding:9px}.answer-k{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.08em}.answer-v{font:700 13px 'JetBrains Mono';color:var(--text);margin-top:3px;line-height:1.25}.answer-v.small{font-family:'IBM Plex Sans';font-size:12px;font-weight:650}
.recommend{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0 0 12px}.rec-card{border:1px solid rgba(255,255,255,.08);border-radius:8px;padding:11px;background:rgba(255,255,255,.025)}.rec-card.primary{border-color:rgba(52,211,153,.25);background:rgba(52,211,153,.06)}.rec-h{font-size:9px;text-transform:uppercase;letter-spacing:.09em;color:var(--text3);margin-bottom:5px}.rec-main{font-weight:800;color:var(--text);font-size:14px}.rec-list{margin-top:7px;display:grid;gap:3px;font-size:11px;color:var(--text2)}.rec-list span{display:block}
.why-card{border:1px solid rgba(99,102,241,.22);background:rgba(99,102,241,.055);border-radius:8px;padding:13px;margin:0 0 12px}.why-title{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#c7d2fe;font-weight:800;margin-bottom:7px}.why-main{font-weight:800;color:var(--text);font-size:15px;margin-bottom:7px}.why-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.why-m{background:rgba(0,0,0,.16);border:1px solid rgba(255,255,255,.06);border-radius:6px;padding:8px}.why-k{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:.08em}.why-v{font:800 13px 'JetBrains Mono';color:var(--text);margin-top:2px}.why-d{font-size:10px;color:var(--text3);line-height:1.35;margin-top:3px}
.primary-actions{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 12px}.primary-actions .tool{border:1px solid rgba(255,255,255,.09);background:rgba(255,255,255,.035)}
.adv{border:1px solid rgba(255,255,255,.08);border-radius:8px;margin-bottom:12px;background:rgba(255,255,255,.018);overflow:hidden}.adv summary{cursor:pointer;padding:10px 12px;font-weight:700;color:var(--text2);font-size:12px;list-style:none}.adv summary::-webkit-details-marker{display:none}.adv summary::after{content:'▾';float:right;color:var(--text3)}.adv[open] summary::after{transform:rotate(180deg)}
.method-grid,.compare-grid{display:grid;gap:7px;padding:0 12px 12px}.pipe{display:grid;grid-template-columns:26px 1fr;gap:8px;align-items:start}.pipe-num{width:22px;height:22px;border-radius:50%;background:rgba(99,102,241,.18);color:#c7d2fe;display:flex;align-items:center;justify-content:center;font:700 10px 'JetBrains Mono'}.pipe-t{font-weight:700;color:var(--text);font-size:12px}.pipe-d{font-size:11px;color:var(--text3);line-height:1.35}
.compare-row{display:grid;grid-template-columns:1fr .8fr .9fr;gap:8px;padding:7px 0;border-top:1px solid rgba(255,255,255,.06);font-size:11px;color:var(--text2)}.compare-row:first-child{border-top:0;color:var(--text3);text-transform:uppercase;letter-spacing:.06em;font-weight:700;font-size:9px}.compare-row b{color:var(--text)}
.evidence{padding:0 12px 12px;font-size:11px;color:var(--text3);line-height:1.5}.evidence b{color:var(--text2)}
.scope-grid{display:grid;gap:7px;padding:0 12px 12px}.scope-row{display:grid;grid-template-columns:92px 1fr;gap:10px;border-top:1px solid rgba(255,255,255,.06);padding:8px 0;font-size:11px}.scope-row:first-child{border-top:0}.scope-tag{font:800 9px 'JetBrains Mono';text-transform:uppercase;letter-spacing:.06em;border-radius:4px;padding:3px 6px;text-align:center;height:fit-content}.scope-tag.ok{background:rgba(52,211,153,.12);color:#34d399}.scope-tag.lim{background:rgba(251,191,36,.12);color:#fbbf24}.scope-tag.no{background:rgba(248,113,113,.12);color:#f87171}.scope-claim{font-weight:800;color:var(--text);margin-bottom:2px}.scope-proof{color:var(--text3);line-height:1.35}
.phase-legend{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px}.phase-pill{border:1px solid rgba(255,255,255,.08);border-radius:6px;padding:6px 8px;font-size:10px;color:var(--text2);background:rgba(255,255,255,.025)}.phase-pill b{display:block;color:var(--text);font-size:11px}
.phase-mode{display:flex;gap:6px;margin:8px 0}.phase-mode button{flex:1;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.03);color:var(--text3);border-radius:6px;padding:5px 6px;font:700 9px 'IBM Plex Sans';letter-spacing:.06em;text-transform:uppercase;cursor:pointer}.phase-mode button.on{color:#fff;background:rgba(99,102,241,.32);border-color:rgba(99,102,241,.55)}
.research3d{display:none;border:1px solid var(--bd);border-radius:8px;background:#0a0a0e;margin-top:8px;padding:8px}.research3d.on{display:block}.cube3d{height:210px;position:relative;overflow:hidden;cursor:grab;touch-action:none}.cube3d:active{cursor:grabbing}.cube-gridline{position:absolute;height:1px;background:rgba(255,255,255,.08);transform-origin:left center}.cube-edge{position:absolute;height:1px;background:rgba(255,255,255,.18);transform-origin:left center}.cube-axis{position:absolute;font:700 9px 'JetBrains Mono';color:#64748b;pointer-events:none}.cube-axis.m{left:9px;top:18px}.cube-axis.s{right:16px;bottom:22px}.cube-axis.c{right:22px;top:22px;color:#fbbf24}.cube-dot{position:absolute;width:9px;height:9px;border-radius:50%;background:#fff;box-shadow:0 0 12px rgba(255,255,255,.55);transform:translate(-4.5px,-4.5px);border:1px solid rgba(0,0,0,.35);cursor:pointer}.cube-dot:hover{outline:2px solid rgba(255,255,255,.65);z-index:6}.cube-label{position:absolute;font-size:9px;color:#94a3b8;white-space:nowrap;pointer-events:none;text-shadow:0 1px 4px #000}.cube-ctrl{display:grid;grid-template-columns:28px 28px 28px;grid-template-rows:24px 24px;gap:4px;justify-content:center;margin:6px 0}.cube-ctrl button{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);color:#cbd5e1;border-radius:5px;font:800 12px 'JetBrains Mono';cursor:pointer}.cube-ctrl button:hover{background:rgba(99,102,241,.24);border-color:rgba(99,102,241,.5)}.cube-readout{font:10px 'JetBrains Mono';color:#64748b;text-align:center;margin-top:-2px}.frontier-note{font-size:10px;color:#64748b;line-height:1.35;margin-top:6px}
.landscape-card{border:1px solid rgba(249,115,22,.42);background:linear-gradient(180deg,rgba(249,115,22,.075),rgba(255,255,255,.018));border-radius:10px;padding:12px;margin:0 0 12px;box-shadow:0 0 0 1px rgba(249,115,22,.08),0 14px 36px rgba(0,0,0,.22)}
.landscape-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:10px}.landscape-kicker{font-size:9px;color:#f59e0b;font-weight:900;letter-spacing:.12em;text-transform:uppercase}.landscape-title{font-size:15px;color:#f8fafc;font-weight:850;line-height:1.2;margin-top:2px}.landscape-sub{font-size:11px;color:#94a3b8;line-height:1.35;margin-top:4px;max-width:620px}.landscape-tag{font:800 9px 'JetBrains Mono';color:#fed7aa;border:1px solid rgba(249,115,22,.28);background:rgba(249,115,22,.1);border-radius:999px;padding:4px 8px;white-space:nowrap}
.landscape-grid{display:grid;grid-template-columns:minmax(0,1fr) 178px;gap:10px;align-items:start}.landscape-map{min-width:0}.landscape-card #phase{width:100%;max-width:none;min-height:220px;border-color:rgba(249,115,22,.28);box-shadow:inset 0 0 28px rgba(0,0,0,.35)}
.landscape-card .phase-mode{margin:0 0 8px}.landscape-card .phase-mode button{font-size:10px;padding:7px 8px}.landscape-card .research3d{margin-top:0;border-color:rgba(249,115,22,.25)}.landscape-card.is-3d #phase{display:none}.landscape-card .cube3d{height:198px}.landscape-card .phase-legend{grid-template-columns:1fr;margin-top:0}.landscape-side{display:grid;gap:8px}.density-bar{height:10px;border-radius:999px;background:linear-gradient(90deg,#2dd4bf 0%,#60a5fa 34%,#fbbf24 68%,#f87171 100%);box-shadow:0 0 20px rgba(96,165,250,.18)}.density-labels{display:flex;justify-content:space-between;font-size:9px;color:#64748b;margin-top:3px}.landscape-note{font-size:10px;color:#94a3b8;line-height:1.45;border:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.16);border-radius:7px;padding:8px}.landscape-note b{color:#e2e8f0}.side .side-explorer-note{font-size:11px;color:#94a3b8;line-height:1.45;border:1px solid rgba(99,102,241,.16);background:rgba(99,102,241,.045);border-radius:8px;padding:10px}
.lim-foot{border-top:1px solid rgba(255,255,255,.07);padding:8px 14px;color:#64748b;font-size:10px}.lim-foot details summary{cursor:pointer;color:#94a3b8;font-weight:700}.lim-foot ul{margin:7px 0 0 14px;padding:0}.lim-foot li{margin:5px 0;line-height:1.35}
.dp-plan{display:grid;gap:8px}.dp-plan-row{border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.025);border-radius:8px;padding:10px}.dp-plan-h{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:#e2e8f0;font-weight:800}.dp-plan-tag{font:800 9px 'JetBrains Mono';color:#34d399;background:rgba(52,211,153,.12);border-radius:4px;padding:2px 5px;white-space:nowrap}.dp-plan-d{font-size:11px;color:#94a3b8;line-height:1.42;margin-top:5px}.dp-plan-proof{font:10px 'JetBrains Mono';color:#64748b;margin-top:6px}
.demo-box{border:1px solid rgba(99,102,241,.18);background:rgba(99,102,241,.04);border-radius:8px;padding:10px;margin:0 0 12px}.demo-title{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent2);font-weight:800;margin-bottom:8px}.demo-actions{display:grid;grid-template-columns:1fr 1fr;gap:7px}.demo-actions .tool{border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.035)}
pre{background:var(--bg);border-radius:6px;padding:12px;font:400 12px/1.5 'JetBrains Mono';white-space:pre-wrap;color:var(--ts)}
.log{font:400 12px/1.7 'JetBrains Mono';color:var(--ts)}.log .ok{color:var(--green)}.log .k{color:var(--vio2)}.log .warn2{color:var(--warn)}
.langtog{background:rgba(255,255,255,0.06);color:#cbd5e1;border:1px solid rgba(255,255,255,0.14);border-radius:5px;padding:4px 9px;font:700 10px 'JetBrains Mono';letter-spacing:.08em;cursor:pointer;margin-right:8px}.langtog:hover{background:rgba(255,255,255,0.12)}
#builder-modal{position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:20000;display:none;align-items:center;justify-content:center}
#builder-modal.open{display:flex}
.bm-card.lab{background:var(--surface);border:1px solid var(--border);border-radius:12px;width:min(940px,95vw);height:min(640px,92vh);display:flex;flex-direction:column;box-shadow:0 24px 70px rgba(0,0,0,0.6);overflow:hidden}
.bm-head{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border);font-weight:700;color:var(--text)}
/* A5 toolbar fina */
.bm-toolbar{display:flex;align-items:center;gap:12px;height:38px;padding:0 14px;border-bottom:1px solid var(--border);background:var(--bg)}
.bm-tb{width:28px;height:24px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;color:var(--text2);cursor:pointer;font-size:14px}.bm-tb:hover{color:var(--text);border-color:var(--accent)}
.bm-tlabel{font-size:11px;color:var(--text3);text-transform:uppercase;letter-spacing:.05em}
.bm-nslider{width:130px;accent-color:var(--accent)}
.bm-nval{font:700 13px 'JetBrains Mono';color:var(--text);min-width:18px}
.bm-angle{width:62px;height:23px;background:var(--surface2);border:1px solid var(--border);border-radius:5px;color:var(--text);font:700 11px 'JetBrains Mono';padding:0 6px}
.bm-status{font-size:11px;color:var(--accent2);font-family:'JetBrains Mono'}
/* A1 dos columnas */
.bm-lab{flex:1;display:flex;min-height:0}
.bm-palette{width:240px;flex-shrink:0;border-right:1px solid var(--border);overflow-y:auto;padding:12px;background:var(--bg)}
.bm-canvas{flex:1;overflow:auto;padding:14px;background:#0a0a0e}
.bm-tb.on{background:var(--accent);color:#fff;border-color:var(--accent)}
.bstate-grid{display:flex;gap:14px;padding:14px;flex-wrap:wrap;align-content:flex-start}
.bstate-card{background:#0a0a0e;border:1px solid var(--border);border-radius:8px;padding:10px}
.bstate-h{font:700 10px 'IBM Plex Sans';letter-spacing:.08em;text-transform:uppercase;color:var(--text3);margin-bottom:8px}
.bstate-empty{padding:28px;color:var(--text2);font-size:12px}
.bg-rect{transform-box:fill-box;transform-origin:center;transition:transform .12s,filter .12s}
.bg-rect.hot{filter:brightness(1.25) drop-shadow(0 0 5px rgba(255,255,255,.35));transform:scale(1.12)}
.bg-cell:focus{outline:none;stroke:var(--accent2);stroke-width:1.5}
/* A2 paleta categorizada */
.bcat{margin-bottom:16px}
.bcat-h{font:700 10px 'IBM Plex Sans';letter-spacing:.1em;text-transform:uppercase;color:var(--text3);margin-bottom:8px;border-bottom:1px solid var(--border);padding-bottom:4px}
.bcat-g{display:flex;flex-wrap:wrap;gap:6px}
.bgate{width:44px;height:44px;border:none;border-radius:8px;color:#fff;font:700 13px 'IBM Plex Sans';cursor:grab;box-shadow:0 2px 4px rgba(0,0,0,0.4);transition:transform .12s,filter .12s;display:flex;align-items:center;justify-content:center}
.bgate:hover{filter:brightness(1.15)}
.bgate.sel{outline:2px solid #fff;outline-offset:1px;transform:scale(1.08)}
.bcat-hint{font-size:9.5px;color:var(--text3);margin-top:7px;line-height:1.4}
/* A4 footer */
.bm-foot{display:flex;align-items:center;gap:14px;padding:10px 16px;border-top:1px solid var(--border);background:var(--bg)}
.bm-metrics{font:600 12px 'JetBrains Mono';color:var(--text2);white-space:nowrap}
.bm-divider{width:1px;height:30px;background:var(--border)}
.bm-qasm{flex:1;height:54px;background:#0a0a0e;color:var(--text2);border:1px solid var(--border);border-radius:6px;padding:6px 8px;font:400 10.5px 'JetBrains Mono';resize:none;line-height:1.5}
.bm-actions{display:flex;gap:8px;flex-shrink:0}
.bm-x{background:none;border:none;color:#a0a0ad;font-size:16px;cursor:pointer}.bm-x:hover{color:#fff}
.bm-body{padding:14px 16px;overflow:auto}
.bm-pal{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.bpal{background:#1c1c24;color:#cbd5e1;border:1px solid #2a2a36;border-radius:6px;padding:6px 12px;font:700 12px 'JetBrains Mono';cursor:pointer}
.bpal.on{background:linear-gradient(135deg,#8b5cf6,#6366f1);color:#fff;border-color:transparent}
.bm-row{display:flex;align-items:center;gap:8px;margin-bottom:10px}.bm-row label{font-size:11px;color:#a0a0ad}
.bm-row input{width:54px;background:#0f1628;color:#e2e8f0;border:1px solid #2a2a36;border-radius:5px;padding:4px 6px;font-family:'JetBrains Mono'}
.bm-status{font-size:11px;color:#a78bfa;font-family:'JetBrains Mono'}
.bm-qubits{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.bq{background:#1c1c24;color:#94a3b8;border:1px solid #2a2a36;border-radius:5px;padding:5px 10px;font:600 11px 'JetBrains Mono';cursor:pointer}.bq:hover{border-color:#8b5cf6;color:#e8e8ee}.bq.pend{background:rgba(139,92,246,0.25);color:#fff;border-color:#8b5cf6}
.bm-circ{background:#0a0a0e;border-radius:8px;min-height:80px;overflow-x:auto}
.bm-foot{padding:12px 16px;border-top:1px solid #26262f;text-align:right}
.status{height:30px;display:flex;align-items:center;gap:16px;padding:0 16px;background:var(--p1);border-top:1px solid var(--bd);
font:400 11px 'JetBrains Mono';color:var(--th)}.status .g{color:var(--green)}.status .sp{flex:1}
.empty{color:var(--th);font-size:12px;text-align:center;padding:30px}
/* PATCH: phase svg + polish */
#phase{border-radius:10px;border:1px solid rgba(255,255,255,0.08);background:#0a0a0e;overflow:hidden}
.mcard .val{padding:2px 8px;background:rgba(255,255,255,0.05);border-radius:4px}
.mcard.hl .val{background:rgba(139,92,246,0.2);color:#c4b5fd}
.chip{border:1px solid transparent}.c-magic{border-color:rgba(139,92,246,0.35)}.c-libro{border-color:rgba(45,212,191,0.35)}
.c-mps{border-color:rgba(96,165,250,0.35)}.c-spread{border-color:rgba(52,211,153,0.35)}.c-tw{border-color:rgba(255,255,255,0.12)}
.verd{border-radius:0 8px 8px 0;animation:slide-in .2s cubic-bezier(.16,1,.3,1)}
@keyframes slide-in{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
.side::-webkit-scrollbar{width:4px}.side::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.1);border-radius:2px}
.outbody::-webkit-scrollbar{width:4px}.outbody::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:2px}
.warn{background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.2);border-radius:6px;padding:8px 10px;line-height:1.5}
.hero{box-shadow:0 0 20px rgba(99,102,241,0.3);transition:filter .15s,box-shadow .15s}.hero:hover{box-shadow:0 0 30px rgba(99,102,241,0.5)}
/* ===== DECISION PANEL ===== */
#decision-panel{position:fixed;top:0;right:0;bottom:0;width:420px;background:#0a0a0f;border-left:1px solid rgba(255,255,255,0.08);z-index:9999;display:flex;flex-direction:column;box-shadow:-20px 0 60px rgba(0,0,0,0.6);transform:translateX(100%);transition:transform .35s cubic-bezier(0.4,0,0.2,1)}
#decision-panel.open{transform:translateX(0)}
.side #decision-panel{position:static;width:auto;min-height:calc(100vh - 170px);border-left:0;box-shadow:none;transform:none;background:transparent;z-index:auto;transition:none}
.side #decision-panel .dp-close{display:none}
.side #decision-panel .dp-header{display:none}
#decision-toggle{display:none;position:fixed;top:50%;right:0;transform:translateY(-50%);z-index:10000;width:42px;background:linear-gradient(160deg,rgba(99,102,241,.95),rgba(139,92,246,.95));color:#fff;border:none;border-radius:10px 0 0 10px;padding:16px 0;cursor:pointer;writing-mode:vertical-rl;text-orientation:mixed;font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;transition:filter .2s;box-shadow:-4px 0 24px rgba(99,102,241,0.48)}
#decision-toggle:hover{filter:brightness(1.2)}
/* ===== A11Y + ergonomia (auditoria UI/UX) ===== */
*:focus-visible{outline:2px solid #818cf8 !important;outline-offset:2px;border-radius:4px}   /* A4 focus ring */
.spin{display:inline-block;animation:spin .8s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.tool.hero.busy{opacity:.7;cursor:progress}
.btn-spinner{display:inline-block;width:11px;height:11px;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;vertical-align:-1px}
.verd.loading{min-height:52px;border:none;background:linear-gradient(90deg,var(--surface) 25%,var(--surface2) 50%,var(--surface) 75%);background-size:200% 100%;animation:shimmer 1.2s infinite;border-radius:8px;padding:0}
@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.mhead .tool,.mhead .tool.hero{height:32px;display:inline-flex;align-items:center;box-sizing:border-box}  /* R11 alturas consistentes */
.circ-head{background:var(--p1,#141419);padding-top:6px}   /* no-sticky: #circ-inline ya tiene su propio scroll, la barra no debe flotar al scrollear */
#noise-p{accent-color:#fbbf24;height:5px;cursor:pointer}                                                  /* R12 slider */
#decision-toggle.has-result::after{content:'';position:absolute;top:6px;left:-3px;width:9px;height:9px;background:#34d399;border-radius:50%;box-shadow:0 0 0 0 rgba(52,211,153,.7);animation:dppulse 1.6s infinite}
@keyframes dppulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.6)}70%{box-shadow:0 0 0 7px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
.main.ed-min .edwrap{height:0;min-height:0;overflow:hidden;border:none}                                   /* R1 editor colapsado */
.main.ed-min .lines{display:none}
#edtoggle{margin-left:6px}
.dp-index{position:sticky;top:0;background:#12121a;padding:8px 16px;border-bottom:1px solid #26262f;font:600 10px 'JetBrains Mono';color:#64748b;z-index:6;letter-spacing:.05em}
.dp-index a{color:#818cf8;text-decoration:none;padding:0 2px}.dp-index a:hover{color:#a78bfa}
#onbtip{position:absolute;top:56px;right:18px;max-width:280px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;padding:12px 14px;border-radius:10px;font-size:12px;line-height:1.5;z-index:9000;box-shadow:0 12px 40px rgba(99,102,241,.4)}
#onbtip button{margin-top:8px;background:rgba(255,255,255,.2);color:#fff;border:none;border-radius:5px;padding:4px 12px;font-size:11px;font-weight:700;cursor:pointer}
#onbtip::before{content:'';position:absolute;top:-7px;right:90px;border:7px solid transparent;border-top:0;border-bottom-color:#6366f1}
.exmenu{position:absolute;top:34px;left:0;background:#1c1c24;border:1px solid #2a2a36;border-radius:6px;padding:4px;z-index:200;min-width:180px;box-shadow:0 10px 30px rgba(0,0,0,.5)}
.exmenu button{display:block;width:100%;text-align:left;background:none;border:none;color:#cbd5e1;padding:6px 10px;font-size:11px;cursor:pointer;border-radius:4px}.exmenu button:hover{background:rgba(139,92,246,.2);color:#fff}
/* B2 — barra de modo full-width estilo IBM (pills) */
.modebar{display:flex;gap:10px;height:36px;align-items:center;padding:0 14px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0}
.modetabs{display:flex;gap:8px;align-items:center}
.modetabs::after{content:'';width:1px;height:18px;background:var(--border);margin-left:2px}   /* separador: las 3 rutas, una accion distinta */
.modetab.mkbuild{color:var(--accent2);border:1px solid var(--accent);background:rgba(99,102,241,0.08)}
.modetab.mkbuild:hover{background:var(--accent);color:#fff}
.modetab{display:inline-flex;align-items:center;gap:7px;background:transparent;border:none;color:var(--text2);padding:5px 14px;font:600 12.5px 'IBM Plex Sans';cursor:pointer;border-radius:6px;height:26px}
.modetab:hover{background:var(--surface2);color:var(--text)}
.modetab.active{background:var(--accent);color:#fff}
.modetab .mdot{width:6px;height:6px;border-radius:50%;background:#475569}.modetab.active .mdot{background:#fff;box-shadow:0 0 6px rgba(255,255,255,.6)}
/* V2-2: workspaces (Author/Triage/Explore) */
.wsseg{display:inline-flex;background:var(--surface2);border:1px solid var(--bd);border-radius:8px;padding:3px;gap:2px}
.wstab{display:inline-flex;align-items:center;gap:6px;background:transparent;border:none;color:var(--text2);padding:5px 14px;font:600 12px 'IBM Plex Sans';cursor:pointer;border-radius:6px;height:26px}
.wstab.active{background:var(--accent);color:#fff}
.wstab:hover:not(.active){color:#e2e8f0}
.ws-sub{display:inline-flex;align-items:center;gap:8px;margin-left:8px;padding-left:10px;border-left:1px solid var(--bd)}
.ws-sublbl{font:600 10px 'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.06em;color:var(--text3)}
.act-build{display:inline-flex;align-items:center;gap:7px;background:rgba(99,102,241,0.08);border:1px solid var(--accent);color:var(--accent2);padding:5px 14px;font:600 12px 'IBM Plex Sans';cursor:pointer;border-radius:6px;height:26px}
.act-build:hover{background:var(--accent);color:#fff}
/* each workspace leads its content; nothing is removed from the DOM */
body.ws-author .worksum{width:46%}body.ws-author .edwrap{flex:1 1 54%}
body.ws-author .diag-explorer,body.ws-triage .diag-explorer{display:none}
body.ws-explore .diag-primary{display:none}
/* Explore lidera SOLO el mapa: oculta las secciones de veredicto que cuelgan de pSummary */
body.ws-explore #pSummary > :not(.diag-grid):not(.empty){display:none}
body.ws-author .diag-grid,body.ws-triage .diag-grid,body.ws-explore .diag-grid{grid-template-columns:1fr}
body.ws-triage .worksum,body.ws-explore .worksum{width:64%!important}
body.ws-triage .edwrap,body.ws-explore .edwrap{flex:1 1 36%!important}
/* Mapa 2D: acotar el tamano visual (el SVG viewBox 260x180 con width:100% se inflaba "enorme"
   a 76% de ancho). Cap de ancho del card + alto del SVG; preserveAspectRatio centra el dibujo. */
body.ws-explore .landscape-card,body.ws-triage .landscape-card{max-width:600px;margin-left:0;margin-right:auto}
body.ws-explore .landscape-card #phase,body.ws-triage .landscape-card #phase{max-height:380px;min-height:200px}
@media(max-width:760px){.ws-sub{display:none!important}}
/* V2-3: stepper (loop explícito Definir→Explorar→Medir→Decidir) */
.atlas-stepper{display:flex;align-items:center;gap:0;padding:7px 18px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0}
.atlas-step{display:flex;align-items:center;gap:8px;padding:5px 12px;border-radius:7px;cursor:pointer;background:transparent;border:none;text-align:left}
.atlas-step:hover{background:rgba(255,255,255,.03)}
.atlas-step.active{background:rgba(99,102,241,.14)}
.atlas-step-num{width:21px;height:21px;border-radius:50%;background:var(--surface2);color:var(--text2);border:1px solid var(--bd);display:flex;align-items:center;justify-content:center;font:700 10px 'IBM Plex Sans';flex-shrink:0}
.atlas-step.active .atlas-step-num{background:var(--accent);color:#fff;border-color:var(--accent)}
.atlas-step.done .atlas-step-num{background:var(--green);color:#0c0c10;border-color:var(--green)}
.atlas-step-label{font:600 11px 'IBM Plex Sans';color:var(--text2);line-height:1.15}
.atlas-step.active .atlas-step-label{color:var(--text)}
.atlas-step-label small{display:block;font:400 9px 'JetBrains Mono',monospace;color:var(--text3);margin-top:1px}
.atlas-step-conn{flex:1 1 16px;height:1px;background:var(--bd);min-width:12px}
@media(max-width:760px){.atlas-step-label{display:none}.atlas-stepper{justify-content:center;gap:4px}.atlas-step-conn{flex:0 0 16px}}
/* V2-4: CTA del loop — el veredicto termina en una acción recomendada (M5) */
.triage-cta{display:flex;flex-direction:column;gap:2px;width:100%;text-align:left;margin:11px 0 4px;padding:11px 14px;border:1px solid var(--accent);border-radius:9px;background:linear-gradient(135deg,rgba(99,102,241,.16),rgba(139,92,246,.08));cursor:pointer;color:var(--text);transition:background .15s}
.triage-cta:hover{background:linear-gradient(135deg,rgba(99,102,241,.28),rgba(139,92,246,.15))}
.triage-cta-k{font:600 9.5px 'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.06em;color:var(--accent2)}
.triage-cta-main{font:700 14px 'IBM Plex Sans';color:var(--text)}
.triage-cta-go{font:600 11px 'IBM Plex Sans';color:var(--accent2);align-self:flex-end;margin-top:1px}
/* R1 — handle de redimensionado */
.rsz{display:none}   /* layout en zonas fijas: editor+resumen arriba, circuito abajo (sin resize) */
.rsz:hover,.rsz.drag{background:rgba(139,92,246,.18)}
.rsz-grip{width:34px;height:3px;border-radius:2px;background:#475569}.rsz:hover .rsz-grip,.rsz.drag .rsz-grip{background:#8b5cf6}
/* A10 — responsive (LinkedIn = trafico movil; el demo debe sobrevivir el clic desde el telefono) */
@media (max-width:860px){
  html,body{height:auto;overflow:auto}
  .topbar{height:auto;flex-wrap:wrap;gap:10px;padding:8px 12px}
  .app{flex-direction:column;height:auto}
  .side{width:100%;order:2;border-left:none;border-top:1px solid var(--bd);max-height:none}
  .main{order:1;min-height:70vh}
  #phase{max-width:420px;margin:0 auto;display:block}
  .outbody{height:auto !important;min-height:300px}
  .worktop{flex-direction:column;min-height:0}        /* en movil: editor encima del resumen */
  .worksum{width:100%;border-left:none;border-top:1px solid var(--bd);max-height:none}
  .tool,.modetab,.otab{min-height:42px}               /* touch targets >=42px */
  .playbtn,.langtog{min-height:36px}
  #decision-panel{width:100vw;max-width:100vw}
  #decision-toggle{top:auto;bottom:12px;transform:none;writing-mode:horizontal-tb;border-radius:8px;padding:10px 14px}
  .dp-matrix{grid-template-columns:1fr 1fr}
}
@media (max-width:480px){.modetab{padding:9px 10px;font-size:12px}.mhead{flex-wrap:wrap}.dp-matrix{grid-template-columns:1fr}}
.dp-header{padding:20px 20px 16px;border-bottom:1px solid rgba(255,255,255,0.07);background:linear-gradient(135deg,rgba(99,102,241,0.1),rgba(139,92,246,0.05))}
.dp-header-top{display:flex;align-items:center;justify-content:space-between}
.dp-logo{display:flex;align-items:center;gap:8px}.dp-logo-icon{width:28px;height:28px;background:linear-gradient(135deg,#6366f1,#8b5cf6);border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:14px}
.dp-title{font-size:13px;font-weight:700;color:#e2e8f0}.dp-subtitle{font-size:10px;color:#64748b;letter-spacing:.08em;text-transform:uppercase}
.dp-close{background:none;border:none;color:#475569;cursor:pointer;font-size:18px;padding:4px;border-radius:4px}.dp-close:hover{color:#94a3b8}
.dp-body{flex:1;overflow-y:auto;padding:0}.dp-section{padding:16px 20px;border-bottom:1px solid rgba(255,255,255,0.05)}.dp-section:last-child{border-bottom:none}
.dp-section-label{font-size:9px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;margin-bottom:10px;display:flex;align-items:center;gap:6px}
.dp-section-label .label-icon{width:16px;height:16px;border-radius:3px;display:flex;align-items:center;justify-content:center;font-size:9px}
.dp-verdict{border-radius:10px;padding:14px 16px;margin-bottom:10px}.dp-verdict.tractable{background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25)}
.dp-verdict.intractable{background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25)}.dp-verdict.warning{background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.25)}
.dp-verdict-label{font-size:9px;font-weight:700;letter-spacing:.15em;text-transform:uppercase;margin-bottom:4px}.tractable .dp-verdict-label{color:#10b981}.intractable .dp-verdict-label{color:#ef4444}.warning .dp-verdict-label{color:#f59e0b}
.dp-verdict-text{font-size:15px;font-weight:700;color:#f1f5f9;line-height:1.3}.dp-verdict-sub{font-size:11px;color:#94a3b8;margin-top:4px;line-height:1.4}
.dp-sowhat{background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.15);border-radius:8px;padding:12px 14px;margin-bottom:8px}
.dp-sowhat-q{font-size:10px;color:#818cf8;font-weight:600;margin-bottom:6px}.dp-sowhat-a{font-size:13px;color:#cbd5e1;line-height:1.5}.dp-sowhat-a strong{color:#e2e8f0}
.dp-matrix{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px}.dp-matrix-cell{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);border-radius:8px;padding:10px 12px}
.dp-matrix-cell.highlight{background:rgba(99,102,241,0.08);border-color:rgba(99,102,241,0.2)}
.dp-mc-label{font-size:9px;color:#475569;text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px}.dp-mc-value{font-size:14px;font-weight:700;color:#e2e8f0}.dp-mc-sub{font-size:9px;color:#64748b;margin-top:2px}
.dp-assump{background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.18);border-radius:6px;padding:8px 10px;margin-bottom:8px}
.dp-assump-t{font-size:10.5px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px}
.dp-assump-row{display:flex;align-items:center;justify-content:space-between;gap:8px;margin:4px 0}
.dp-assump-row label{font-size:11.5px;color:#cbd5e1}
.dp-assump-row select,.dp-assump-row input{background:#0f1628;color:#e2e8f0;border:1px solid rgba(255,255,255,0.12);border-radius:4px;padding:3px 6px;font-size:11px;font-family:'JetBrains Mono';max-width:60%}
.dp-bd{margin-bottom:8px;border:1px solid rgba(255,255,255,0.07);border-radius:6px;overflow:hidden}
.dp-bd-h{font-size:10px;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;padding:6px 10px;background:rgba(255,255,255,0.03)}
.dp-bd-row{display:grid;grid-template-columns:1.1fr 1.4fr 1fr auto;gap:8px;align-items:center;padding:5px 10px;border-top:1px solid rgba(255,255,255,0.04);font-size:11px}
.dp-bd-k{color:#cbd5e1;font-weight:600}.dp-bd-f{color:#64748b;font-family:'JetBrains Mono';font-size:10px}.dp-bd-v{color:#e2e8f0;font-family:'JetBrains Mono';text-align:right}
.dp-bd-t{font-size:9px;text-transform:uppercase;letter-spacing:.04em;font-weight:700;text-align:right}
.dp-lim{margin:0;padding-left:16px;display:flex;flex-direction:column;gap:6px}.dp-lim li{font-size:11px;color:#94a3b8;line-height:1.5}
.dp-money{display:flex;flex-direction:column;gap:6px}.dp-money-row{display:flex;align-items:flex-start;gap:10px;padding:8px 10px;border-radius:6px;background:rgba(255,255,255,0.02)}
.dp-money-row.good{border-left:2px solid #10b981}.dp-money-row.bad{border-left:2px solid #ef4444}.dp-money-row.neutral{border-left:2px solid #6366f1}
.dp-money-icon{font-size:14px;flex-shrink:0;margin-top:1px}.dp-money-text{font-size:12px;color:#94a3b8;line-height:1.4}.dp-money-text strong{color:#cbd5e1}
.dp-sci{display:flex;flex-direction:column;gap:6px}.dp-sci-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)}.dp-sci-row:last-child{border-bottom:none}
.dp-sci-label{font-size:11px;color:#64748b;display:flex;align-items:center;gap:6px}.dp-sci-label code{background:rgba(255,255,255,0.06);padding:1px 5px;border-radius:3px;font-family:'JetBrains Mono',monospace;font-size:10px;color:#94a3b8}
.dp-sci-val{font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600;color:#e2e8f0;text-align:right}.dp-sci-interp{font-size:9px;color:#475569;text-align:right}
.dp-gauge{margin-bottom:4px}.dp-gauge-label{display:flex;justify-content:space-between;font-size:10px;color:#64748b;margin-bottom:3px}.dp-gauge-track{height:5px;background:rgba(255,255,255,0.06);border-radius:999px;overflow:hidden}.dp-gauge-fill{height:100%;border-radius:999px;transition:width 1s cubic-bezier(0.4,0,0.2,1)}
.dp-rec{background:linear-gradient(135deg,rgba(99,102,241,0.1),rgba(139,92,246,0.06));border:1px solid rgba(99,102,241,0.2);border-radius:10px;padding:14px 16px}
.dp-rec-title{font-size:10px;font-weight:700;color:#818cf8;letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px}.dp-rec-text{font-size:12px;color:#94a3b8;line-height:1.6}.dp-rec-text strong{color:#c7d2fe}
.dp-rec-action{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap}.dp-rec-btn{font-size:10px;font-weight:600;letter-spacing:.06em;padding:5px 10px;border-radius:5px;border:none;cursor:pointer;text-transform:uppercase;transition:all .2s}
.dp-rec-btn.primary{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff}.dp-rec-btn.secondary{background:rgba(255,255,255,0.07);color:#94a3b8}.dp-rec-btn:hover{opacity:.85;transform:translateY(-1px)}
.dp-footer{padding:10px 20px;border-top:1px solid rgba(255,255,255,0.05);font-size:9px;color:#334155;display:flex;justify-content:space-between;align-items:center}
</style></head><body class="ws-author">
<style>html{background:#050507}body{background:transparent !important}
#kreniq-bg{display:none}   /* net Three.js retirada -> logo flotante CANÓNICO (consistencia con CAPAS) */
/* ── CHROME CANÓNICO KRENIQ (idéntico a CAPAS; scoped, no toca la UI tool de Atlas) ── */
.kq-bg-logo{position:fixed;inset:0;z-index:-2;pointer-events:none;overflow:hidden;opacity:.62}
.kq-bg-logo iframe{width:100%;height:100%;border:0;display:block;background:#000;transform:scale(3.35);transform-origin:center center}
.kq-bg-veil{position:fixed;inset:0;z-index:-1;pointer-events:none;background:radial-gradient(circle at 60% 35%,transparent 0%,rgba(5,5,7,.25) 40%,rgba(5,5,7,.62) 100%),linear-gradient(rgba(5,5,7,.40),rgba(5,5,7,.10) 30%,rgba(5,5,7,.5))}
.kq-nav{position:sticky;top:0;z-index:120;display:flex;align-items:center;padding:0 48px;height:60px;border-bottom:1px solid rgba(255,255,255,0.06);background:rgba(8,8,16,0.92);backdrop-filter:blur(12px)}
.kq-nav-logo{display:flex;align-items:center;gap:10px;text-decoration:none;margin-right:40px;flex-shrink:0}
.kq-nav-logo img{width:32px;height:32px;object-fit:contain;display:block}
.kq-nav-logo b{font-size:14px;font-weight:800;color:#fff;letter-spacing:-0.01em;line-height:1.1;display:block}
.kq-nav-logo span{font-size:9px;font-weight:500;color:#444;letter-spacing:0.1em;text-transform:uppercase;display:block}
.kq-nav-links{display:flex;align-items:center;gap:4px}
.kq-nav-links a{display:inline-flex;align-items:center;gap:6px;color:rgba(255,255,255,0.5);text-decoration:none;font-size:13px;padding:7px 14px;border-radius:6px;white-space:nowrap;transition:color .15s}
.kq-nav-links a:hover{color:rgba(255,255,255,0.85)}
.kq-nav-links a.on{color:#fff;border:1px solid rgba(255,255,255,0.18);background:rgba(255,255,255,0.05)}
.kq-nav-sep{flex:1}
.kq-nav-cta{background:linear-gradient(135deg,#e8185d,#c4125a);color:#fff;font-size:13px;font-weight:700;padding:9px 20px;border-radius:7px;text-decoration:none;box-shadow:0 2px 14px rgba(232,24,93,0.35);white-space:nowrap;transition:opacity .15s}
.kq-nav-cta:hover{opacity:.88}
@media(max-width:760px){.kq-nav{padding:0 14px;flex-wrap:wrap;height:auto;gap:6px;padding-top:8px;padding-bottom:8px}.kq-nav-logo{margin-right:0}.kq-nav-links{order:3;width:100%;overflow-x:auto}.kq-nav-sep{display:none}.kq-nav-cta{margin-left:auto}}
</style>
<div class="kq-bg-logo"><iframe src="/vendor/logo_kreniq_volum_trico.html" scrolling="no" tabindex="-1" aria-hidden="true"></iframe></div><div class="kq-bg-veil"></div>
<nav class="kq-nav"><a class="kq-nav-logo" href="https://krenniq.com/"><img src="/vendor/krenniq-logo.png" alt="Krenn-IQ"><span><b>Atlas</b>by Krenn-IQ</span></a>
<div class="kq-nav-links"><a href="https://krenniq.com/"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>Home</a><a href="https://capas.krenniq.com/"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>CAPAS</a><a class="on" href="/"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg>Atlas</a></div>
<div class="kq-nav-sep"></div><a class="kq-nav-cta" href="https://capas.krenniq.com/">Probar un claim</a></nav>
<div id="kreniq-bg"></div><div id="kreniq-veil"></div>
<div class=topbar>
  <div class=brand><span class="logo-net top-logo" aria-hidden="true"><svg viewBox="-34 -34 68 68"><defs><radialGradient id="atlasLogoGlow" cx="50%" cy="50%" r="58%"><stop offset="0%" stop-color="#00e5ff" stop-opacity=".34"/><stop offset="62%" stop-color="#6366f1" stop-opacity=".12"/><stop offset="100%" stop-color="#05060a" stop-opacity="0"/></radialGradient></defs><circle class="core-glow" r="31"/><ellipse class="shell" rx="28" ry="19" transform="rotate(-23)"/><ellipse class="shell" rx="18" ry="28" transform="rotate(34)"/><path class="edge thin" d="M-22 8 Q-4 -5 18 -16"/><path class="edge thin" d="M-16 -18 Q2 0 22 10"/><path class="edge thin" d="M-25 -4 Q-2 14 20 20"/><path class="edge cyan" d="M-19 15 Q-2 -9 17 -18"/><path class="edge cyan" d="M-12 -22 Q4 -1 22 13"/><path class="edge mag" d="M-23 -8 Q1 7 24 -4"/><path class="edge mag" d="M-4 24 Q8 5 14 -20"/><circle class="node gold" cx="-22" cy="8" r="2.6"/><circle class="node gold" cx="-16" cy="-18" r="2.2"/><circle class="node gold" cx="-4" cy="24" r="2.4"/><circle class="node gold" cx="18" cy="-16" r="2.7"/><circle class="node gold" cx="22" cy="13" r="2.5"/><circle class="node hot" cx="-23" cy="-8" r="3.1"/><circle class="node hot" cx="24" cy="-4" r="3.3"/><circle class="node hot" cx="14" cy="-20" r="2.9"/><circle class="node gold" cx="4" cy="3" r="2.1"/></svg></span>Atlas <span class=dim data-i18n=brand>- triage de computo cuantico</span></div>
  <div class=claim>The pre-flight system for quantum compute triage.</div>
  <div class=sp></div>
  <button class=cmdk-trigger id=cmdk-trigger onclick="openPalette()" aria-label="Abrir paleta de comandos" title="Paleta de comandos (Cmd/Ctrl-K)"><span data-i18n=cmdkTrig>Buscar acción</span> <kbd>⌘K</kbd></button>
  <button class=langtog id=langtog onclick="toggleLang()" aria-label="Cambiar idioma (espanol / ingles)" title="Cambiar idioma ES/EN">EN</button>
  <div class=badges><span class=badge id=fmt>OpenQASM 2.0</span><span class="badge v" id=nq>n=0 qubits</span></div>
</div>
<div class=modebar>
  <div class=wsseg role=tablist aria-label="espacio de trabajo">
    <button class="wstab active" id=wsAuthor onclick="setWorkspace('author')" role=tab aria-selected=true aria-label="Workspace Author: crear el circuito">✎ Author</button>
    <button class=wstab id=wsTriage onclick="setWorkspace('triage')" role=tab aria-selected=false aria-label="Workspace Triage: veredicto y que sigue">🔍 Triage</button>
    <button class=wstab id=wsExplore onclick="setWorkspace('explore')" role=tab aria-selected=false aria-label="Workspace Explore: mapa de espacio de diseno">◎ Explore</button>
  </div>
  <div class=ws-sub id=authorSub>
    <span class=ws-sublbl data-i18n=wsCreate>crear:</span>
    <div class=modetabs role=group aria-label="metodo de creacion">
      <button class="modetab active" id=tabDx onclick="mode('dx')" aria-label="Escribir QASM a mano"><span class=mdot></span>QASM</button>
      <button class=modetab id=tabGen onclick="mode('gen')" aria-label="Generar desde parametros"><span class=mdot></span><span data-i18n=tabGen>Generar</span></button>
    </div>
  </div>
  <div class=sp></div>
  <button class=act-build onclick="openBuilder()" aria-label="Abrir el constructor visual de circuitos" title="Construye un circuito visualmente (sin escribir QASM)">⊞ <span data-i18n=tabBuild>Construir</span></button>
</div>
<div class=atlas-stepper id=atlas-stepper role=group aria-label="progreso de triage">
  <button class=atlas-step id=step1 onclick="setWorkspace('author')" aria-label="Paso 1: definir circuito"><span class=atlas-step-num>1</span><span class=atlas-step-label><span data-i18n=stepDef>Definir circuito</span><small id=step1sub>—</small></span></button>
  <span class=atlas-step-conn></span>
  <button class=atlas-step id=step2 onclick="setWorkspace('explore')" aria-label="Paso 2: explorar espacio"><span class=atlas-step-num>2</span><span class=atlas-step-label><span data-i18n=stepExp>Explorar espacio</span><small id=step2sub>—</small></span></button>
  <span class=atlas-step-conn></span>
  <button class=atlas-step id=step3 onclick="setWorkspace('triage')" aria-label="Paso 3: medir dureza"><span class=atlas-step-num>3</span><span class=atlas-step-label><span data-i18n=stepMed>Medir dureza</span><small id=step3sub>—</small></span></button>
  <span class=atlas-step-conn></span>
  <button class=atlas-step id=step4 onclick="setWorkspace('triage');var p=$('decision-panel');if(p&&p.scrollIntoView)p.scrollIntoView({behavior:'smooth'})" aria-label="Paso 4: decidir ruta"><span class=atlas-step-num>4</span><span class=atlas-step-label><span data-i18n=stepDec>Decidir ruta</span><small id=step4sub>—</small></span></button>
</div>
<div class=app>
  <aside class=side>
    <div class=right-actions>
      <button class="right-act good" onclick="otab('Log')">● Analizar trazabilidad ♡</button>
      <button class=right-act onclick="openChat()" title="Pregunta a Claude sobre el diagnostico de este circuito">💬 Ask Chat</button>
      <button class="right-act right-cost" onclick="openGastoDrawer()">＄ Modelo de gasto</button>
    </div>
    <div id="decision-panel" class=open data-lm="decision"></div>
  </aside>
  <main class=main>
    <div class=mhead><span class=fname>circuit.qasm</span><span class=badge>OpenQASM 2.0 / 3.0</span><div class=sp></div>
      <button class=tool onclick="setq('')" data-i18n=btnClear aria-label="Limpiar el editor">Limpiar</button>
      <div style="position:relative;display:inline-block">
        <button class=tool onclick="toggleExamples(event)" aria-haspopup=true aria-expanded=false aria-label="Cargar un circuito de ejemplo"><span data-i18n=btnExample>Ejemplo</span> ▾</button>
        <div id=exmenu class=exmenu hidden role=menu>
          <button role=menuitem onclick="setq(DEMO);hideExamples()">🟢 <span data-i18n=exBasic>Basico (trivial)</span></button>
          <button role=menuitem onclick="hardExample();hideExamples()">🔴 <span data-i18n=exHard>Intractable (2D denso)</span></button>
          <button role=menuitem onclick="setq(CLIFFORD_DEMO);hideExamples()">🔵 <span data-i18n=exCliff>Clifford puro</span></button>
          <button role=menuitem onclick="cliffordBig();hideExamples()">🟣 Clifford grande (n=64) — escala</button>
          <button role=menuitem onclick="deep1D();hideExamples()">🟠 1D profundo (n=24)</button>
        </div></div>
      <button class=tool onclick="exportQASM()" aria-label="Exportar el circuito como archivo .qasm" title="Descargar como archivo .qasm">⤓ QASM</button>
      <button class=tool onclick="exportQIR()" aria-label="Exportar el circuito como QIR (LLVM IR)" title="Descargar como QIR (LLVM IR, base profile) — formato del QIR Alliance / Azure Quantum">⤓ QIR</button>
      <button id=edtoggle class=tool onclick="toggleEditor()" aria-label="Minimizar o expandir el editor de codigo" title="Minimiza el editor para dar mas espacio al resultado">⇕</button>
      <button class="tool hero" id=analyzebtn onclick="analyze()" aria-label="Analizar el circuito (Cmd+Enter)" title="Diagnostica el circuito (Stim/quimb/cotengra) · Cmd+Enter">&#9654; <span data-i18n=btnAnalyze>Analizar</span></button></div>
    <div class=worktop>
    <div class=edwrap data-lm="editor">
      <div class=lines id=lines>1</div>
      <div class=ed-area><pre id=qasm-hl aria-hidden=true></pre><textarea id=qasm spellcheck=false oninput="onInput()" onscroll="syncScroll()" onkeyup="curpos()" onclick="curpos()"></textarea></div>
      <div class=genpanel id=genpanel>
        <div class=gen-controls>
        <div class=gen-head><span class=paso-badge>PASO 1</span><span class=gen-head-t data-i18n=genHead>Generador de familias</span></div>
        <div class=gctrl><label data-i18n=glMagic>magia (densidad de T)</label><div class=seg id=sMagic>
          <button class=on onclick="seg('Magic',this,'high')" data-i18n=segHi>Alto</button><button onclick="seg('Magic',this,'low')" data-i18n=segLo>Bajo</button></div></div>
        <div class=gctrl><label data-i18n=glSpread>spread / entrelazamiento</label><div class=seg id=sSpread>
          <button class=on onclick="seg('Spread',this,'high')" data-i18n=segHi>Alto</button><button onclick="seg('Spread',this,'low')" data-i18n=segLo>Bajo</button></div></div>
        <div class=gctrl><label data-i18n=glBook>estructura</label><div class=seg id=sBook>
          <button class=on onclick="seg('Book',this,'core')">interacting</button><button onclick="seg('Book',this,'free')">free</button></div></div>
        <div class=gctrl><label>treewidth</label><div class=seg id=sTw>
          <button onclick="seg('Tw',this,'high')" data-i18n=segHi>Alto</button><button class=on onclick="seg('Tw',this,'low')" data-i18n=segLo>Bajo</button></div></div>
        <div class=gctrl><label data-i18n=glN for=gn>n qubits</label><input class=gn id=gn type=number value=12 min=4 max=127 aria-label="numero de qubits a generar (hasta 127, escala QPU)"></div>
        <div class=gen-actions>
          <button class="tool hero" onclick="genFromPanel()">&#9654; <span data-i18n=btnGen>Generar circuito</span></button>
          <button class="tool" onclick="genReroll()" aria-label="Variar: nuevo circuito con los mismos parametros" title="Variar (nuevo seed) — mismos dials, otro circuito representativo">&#127922; <span data-i18n=btnVary>Variar</span></button>
        </div>
        <div class=gen-ex>
          <div class=gen-ex-lbl data-i18n=genEx>Ejemplos rápidos</div>
          <button class=gen-ex-btn onclick="setq(DEMO)">🟢 <span data-i18n=exBasic>Basico (trivial)</span></button>
          <button class=gen-ex-btn onclick="hardExample()">🔴 <span data-i18n=exHard>Intractable (2D denso)</span></button>
          <button class=gen-ex-btn onclick="setq(CLIFFORD_DEMO)">🔵 <span data-i18n=exCliff>Clifford puro</span></button>
        </div>
        </div>
        <div id=gen-explorer-slot class=gen-explorer-slot></div>
      </div>
    </div>
    <div class=worksum id=pSummary data-lm="summary"><div class=empty data-i18n=emptyRes>Analiza un circuito para ver su posicion en el diagrama de fases.</div></div>
    <div style="margin-top:12px;font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--text3)">Herramientas</div>
    <div id=certbar style="margin-top:6px;display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:6px">
      <button class=playbtn onclick="atlasCert()" title="Diagnóstico honesto (route-adjudication record): witness + confianza calibrada + driver + alcanzabilidad HW. NO es prueba formal — es evidencia trazable.">📜 Diagnóstico</button>
      <button class=playbtn onclick="atlasHarden()" title="Explora donde el circuito cruza CPU->TENSOR->HPC->ESCALATE y la primera variante dura">🧭 Explorar complejidad</button>
      <button class=playbtn onclick="atlasSegment()" title="Triage por segmento: donde se concentra la dureza en un circuito hibrido">🧩 Segmentos</button>
      <button class=playbtn onclick="atlasGpu()" title="Ruta GPU statevector: si una GPU clasica es mas barata que QPU (frontera dinamica)">🖥️ Ruta GPU</button>
      <button class=playbtn onclick="atlasVar()" title="Triage variacional VQE/QAOA: coste por disparo x #evaluaciones vs presupuesto QPU">🔁 Variacional</button>
      <button class=playbtn onclick="atlasBench()" title="Bundle de benchmark auditable: corpus+hash, matriz de confusion, definicion de la metrica, falsa-seguridad con CI Wilson, baselines">📊 Benchmark</button>
      <button class=playbtn onclick="atlasHardware()" title="Realidad del hardware ibm_kingston (medido): chip efectivo, zona muerta dinamica, dephasing, lo que IBM no sintetiza">🔬 Hardware</button>
      <button class=playbtn onclick="atlasEmulate()" title="Emula la salida RUIDOSA del device con tasas MEDIDAS, sin gastar shots QPU (token-free, n<=16) + embedding sugerido">🔊 Emular ruido</button>
      <button class=playbtn onclick="atlasEmbedding()" title="Advisor de embedding (token-free): sub-grafo de MENOR error CZ desde la tabla medida. Recomienda qubits, los que evitar, suma de error CZ y el contraste medido GOOD-vs-TLS (9.7x ghz6 / 7.3x ghz4).">🎯 Embedding</button>
      <button class=playbtn onclick="atlasReachability()" title="Reachability a CUALQUIER n SIN statevector (mirror-RB): fidelidad efectiva predicha (κ̂-corregida desde calibración medida) + techo realista + el circuito mirror que lo VERIFICA en metal. Polinomial: no ejecuta computo exponencial.">📡 Alcanzabilidad</button>
      <button class=playbtn onclick="atlasCompute()" title="El '+': si el triage CERTIFICA que es barato (Clifford/Stim, o 2^n cabe), computa y entrega la distribucion de salida ideal. Si el caso es duro, dice el veredicto en vez de inventar un numero. Nunca corre el caso duro a ciegas.">▶ Computar resultado</button>
    </div>
    <div id=certPanel style="margin-top:8px;font:12px ui-monospace,SFMono-Regular,monospace;white-space:pre-wrap;color:#cbd5e1;line-height:1.5"></div>
    </div>
    <div class=rsz id=rsz role=separator aria-label="Arrastrar para redimensionar el editor" tabindex=0 title="Arrastra para redimensionar (o usa el boton ⇕)"><div class=rsz-grip></div></div>
    <div class=outhead data-lm="output-head">
      <button class="otab active" id=oResultado onclick="otab('Resultado')" aria-label="Panel de circuito y musica"><span data-i18n=tabResult>Circuito / musica</span> <span class=bdg id=bResultado style=display:none></span></button>
      <button class=otab id=oLog onclick="otab('Log')" aria-label="Pestana de log">Log</button></div>
    <div class=outbody data-lm="output">
      <div class="opane on" id=pResultado><div class=empty data-i18n=emptyCirc>El diagrama del circuito aparecera aqui.</div></div>
      <div class=opane id=pCircuito><div class=empty data-i18n=emptyCirc>El diagrama del circuito aparecera aqui.</div></div>
      <div class=opane id=pQASM><div class=empty data-i18n=emptyQasm>El QASM generado aparecera aqui.</div></div>
      <div class=opane id=pLog><div class=log id=logbody>esperando...</div></div>
    </div>
    <div class=status><span class=g id=st>&#9679; <span data-i18n=stReady>Listo</span></span><span id=pos>Ln 1, Col 1</span><span id=chars>0 chars</span>
      <span class=sp></span><span id=gt>reference engines: Stim / quimb / cotengra</span><span style="margin-left:14px;opacity:.5;font-size:10px;white-space:nowrap">© 2026 Fco. Osvaldo Morales Vilchis &middot; <a href="https://www.apache.org/licenses/LICENSE-2.0" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline">Apache&nbsp;2.0</a></span></div>
  </main>
</div>
<script>
// ===== i18n ES/EN (chrome estatico; la prosa analitica del panel permanece en ES por ahora) =====
var LANG=(function(){try{var m=document.cookie.match(/(?:^|;)\s*kq_lang\s*=\s*([^;]+)/);if(m)return decodeURIComponent(m[1]);var l=localStorage.getItem('kq_lang');if(l)return l;}catch(e){}return 'en';})();  // inglés de entrada; cookie compartida .krenniq.com persiste el idioma entre landing/CAPAS/Atlas
var I18N={en:{brand:'- quantum compute triage',tabDx:'Diagnose',tabGen:'Generate',tabBuild:'Build',cmdkTrig:'Search action',wsCreate:'create:',stepDef:'Define circuit',stepExp:'Explore space',stepMed:'Measure hardness',stepDec:'Decide route',gdSub:'Compute route economics',genHead:'Family generator',genEx:'Quick examples',secPhase:'Design-space explorer: circuit families before diagnosis',
  phint:'The map selects a synthetic circuit family. The red corner is a perceived-hardness challenge, not a QPU recommendation.',secMetrics:'Metrics',secRefs:'References',btnClear:'Clear',
  btnExample:'Example',btnHard:'Hard example',btnAnalyze:'Analyze',glMagic:'magic (T density)',glSpread:'spread / entanglement',
  glBook:'structure',glN:'n qubits',segHi:'High',segLo:'Low',btnGen:'Generate circuit',btnVary:'Vary',tabResult:'Circuit / sound',
  emptyRes:'Analyze a circuit to see its position in the phase diagram.',emptyQasm:'Generated QASM will appear here.',
  tabCirc:'Circuit',emptyCirc:'The circuit diagram will appear here.',btnPlay:'♪ Play',noiseHead:'Noise (2q depolarizing)',
  btnBuilder:'⊞ Builder',builderTitle:'Visual circuit builder',builderN2:'n qubits',builderUndo:'Undo',builderClear:'Clear',builderUse:'▶ Use & analyze',
  exBasic:'Basic (trivial)',exHard:'Stress-test (dense 2D)',exCliff:'Pure Clifford',
  stReady:'Ready',
  noise:'Note: diagnostic is for the COHERENT (noiseless) circuit. Real noise tends to make a circuit MORE classically simulable, so a high index is an UPPER BOUND on hardware behavior.'},
  es:{noise:'Nota: veredicto para el circuito COHERENTE (sin ruido). El ruido real suele hacer el circuito MAS simulable clasicamente, asi que un veredicto duro es COTA SUPERIOR de la dureza en hardware.',
    noiseHead:'Ruido (depolarizante 2q)'}};
function applyLang(){var d=I18N[LANG]||{};document.querySelectorAll('[data-i18n]').forEach(function(el){
  var k=el.getAttribute('data-i18n');if(!el.dataset.orig)el.dataset.orig=el.textContent;  // snapshot ES original
  if(LANG==='es'){el.textContent=(I18N.es&&I18N.es[k]!=null)?I18N.es[k]:el.dataset.orig;}
  else if(d[k]!=null){el.textContent=d[k];}});
  var lt=document.getElementById('langtog');if(lt)lt.textContent=LANG==='es'?'EN':'ES';}
function toggleLang(){LANG=LANG==='es'?'en':'es';
  try{document.cookie='kq_lang='+LANG+';domain=.krenniq.com;path=/;max-age=31536000;SameSite=Lax';document.cookie='kq_lang='+LANG+';path=/;max-age=31536000;SameSite=Lax';localStorage.setItem('kq_lang',LANG);}catch(e){}  // persiste a la cookie compartida
  applyLang();
  if(typeof renderNoise==='function')renderNoise();                 // G1: traducir el cuerpo del noise-box
  var p=document.getElementById('decision-panel');if(p&&p.classList.contains('open'))buildDecisionPanel();}
const DEMO=`%DEMO%`;
const CLIFFORD_DEMO='OPENQASM 2.0;\nqreg q[6];\nh q[0];\nh q[1];\ncx q[0],q[1];\ncx q[1],q[2];\ns q[3];\ncx q[2],q[3];\nh q[4];\ncx q[4],q[5];\ncx q[3],q[4];\n';
function toggleExamples(e){if(e)e.stopPropagation();var m=$('exmenu'),b=e&&e.currentTarget;if(!m)return;var open=m.hasAttribute('hidden');if(open){m.removeAttribute('hidden');if(b)b.setAttribute('aria-expanded','true');}else hideExamples();}
function hideExamples(){var m=$('exmenu');if(m){m.setAttribute('hidden','');var b=m.parentElement.querySelector('button');if(b)b.setAttribute('aria-expanded','false');}}
function toggleEditor(){var m=document.querySelector('main.main');if(m)m.classList.toggle('ed-min');}   // R1
document.addEventListener('click',function(e){var m=$('exmenu');if(m&&!m.hasAttribute('hidden')&&!e.target.closest('#exmenu')&&!(e.target.closest('button')&&/Ejemplo|Example/.test(e.target.textContent)))hideExamples();});
document.addEventListener('keydown',function(e){    // R9 atajos de teclado
  if((e.metaKey||e.ctrlKey)&&(e.key==='k'||e.key==='K')){e.preventDefault();var cp=$('cmdk');if(cp&&cp.classList.contains('open'))closePalette();else openPalette();return;}   // V2-0: Cmd/Ctrl-K
  if((e.metaKey||e.ctrlKey)&&e.key==='Enter'){e.preventDefault();analyze();}
  if(e.key==='Escape'){
    var ck=$('cmdk');if(ck&&ck.classList.contains('open')){closePalette();return;}   // V2-0: Escape cierra la paleta primero
    var gd=$('gasto-drawer');if(gd&&gd.classList.contains('open')){closeGastoDrawer();return;}   // V2-5: Escape cierra el drawer de gasto
    var cm=$('chat-modal');if(cm&&cm.classList.contains('open')){closeChat();return;}   // Fase 6: Escape cierra el chat primero
    var am=$('analysis-modal');if(am&&am.classList.contains('open')){closeAnalysisPanel();return;}   // #1: Escape closes triage modal first
    var bm=$('builder-modal');if(bm&&bm.classList.contains('open')){closeBuilder();return;}
    var p=$('decision-panel');if(p&&p.classList.contains('open')){p.classList.remove('open');var tg=$('decision-toggle');if(tg)tg.setAttribute('aria-expanded','false');}
    hideExamples();}});
let trail=[], curMode='dx';
var ATLAS_FRONTIER=%FRONTIER%;   // data-driven frontier params (benchmarks/build_frontier.py)
const dials={Magic:'high',Spread:'high',Book:'core',Tw:'low'};
function $(id){return document.getElementById(id)}
function atlasLogoSVG(cls){return '<span class="logo-net '+(cls||'')+'" aria-hidden="true"><svg viewBox="-34 -34 68 68"><defs><radialGradient id="atlasLogoGlow" cx="50%" cy="50%" r="58%"><stop offset="0%" stop-color="#00e5ff" stop-opacity=".34"/><stop offset="62%" stop-color="#6366f1" stop-opacity=".12"/><stop offset="100%" stop-color="#05060a" stop-opacity="0"/></radialGradient></defs><circle class="core-glow" r="31"/><ellipse class="shell" rx="28" ry="19" transform="rotate(-23)"/><ellipse class="shell" rx="18" ry="28" transform="rotate(34)"/><path class="edge thin" d="M-22 8 Q-4 -5 18 -16"/><path class="edge thin" d="M-16 -18 Q2 0 22 10"/><path class="edge thin" d="M-25 -4 Q-2 14 20 20"/><path class="edge cyan" d="M-19 15 Q-2 -9 17 -18"/><path class="edge cyan" d="M-12 -22 Q4 -1 22 13"/><path class="edge mag" d="M-23 -8 Q1 7 24 -4"/><path class="edge mag" d="M-4 24 Q8 5 14 -20"/><circle class="node gold" cx="-22" cy="8" r="2.6"/><circle class="node gold" cx="-16" cy="-18" r="2.2"/><circle class="node gold" cx="-4" cy="24" r="2.4"/><circle class="node gold" cx="18" cy="-16" r="2.7"/><circle class="node gold" cx="22" cy="13" r="2.5"/><circle class="node hot" cx="-23" cy="-8" r="3.1"/><circle class="node hot" cx="24" cy="-4" r="3.3"/><circle class="node hot" cx="14" cy="-20" r="2.9"/><circle class="node gold" cx="4" cy="3" r="2.1"/></svg></span>'}
function designExplorerHTML(){
  var EN=LANG==='en';
  return `<section class=landscape-card data-lm="explorer">
    <div class=landscape-head><div><div class=landscape-kicker>${EN?'Design-space explorer':'Explorador de espacio de diseno'}</div><div class=landscape-title>${EN?'Circuit families before diagnosis':'Familias antes del diagnostico'}</div><div class=landscape-sub>${EN?'Axes represent generator intentions. The verdict is assigned only after Atlas measures spread, MPS, treewidth and physical checks.':'Los ejes representan intenciones del generador. El veredicto se obtiene solo despues de medir spread, MPS, treewidth y checks fisicos.'}</div></div><div class=landscape-tag>${EN?'family ≠ outcome':'familia ≠ outcome'}</div></div>
    <div class=landscape-grid><div class=landscape-map>
      <div class=phase-mode><button id=ph2db class=on onclick="phaseMode('2d')">2D Explorer</button><button id=ph3db onclick="phaseMode('3d')">3D Research</button><button id=phmeas onclick="runMeasuredTrajectory()" title="${EN?'Animate the measured complexity climb gate-by-gate (real MPS/treewidth per prefix)':'Anima el avance medido sobre la complejidad compuerta a compuerta (MPS/treewidth reales por prefijo)'}">◉ ${EN?'Measured climb':'Avance medido'}</button></div>
      <svg id=phase viewBox="0 0 260 180" onclick="clickPhase(event)">
      <defs>
        <radialGradient id="gLow" cx="11%" cy="93%" r="58%"><stop offset="0%" stop-color="#10b981" stop-opacity="0.55"/><stop offset="100%" stop-color="#10b981" stop-opacity="0"/></radialGradient>
        <radialGradient id="gMagic" cx="9%" cy="10%" r="56%"><stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.62"/><stop offset="100%" stop-color="#8b5cf6" stop-opacity="0"/></radialGradient>
        <radialGradient id="gSpr" cx="50%" cy="100%" r="55%"><stop offset="0%" stop-color="#14b8a6" stop-opacity="0.5"/><stop offset="100%" stop-color="#14b8a6" stop-opacity="0"/></radialGradient>
        <radialGradient id="gGrid" cx="45%" cy="50%" r="40%"><stop offset="0%" stop-color="#3b82f6" stop-opacity="0.42"/><stop offset="100%" stop-color="#3b82f6" stop-opacity="0"/></radialGradient>
        <radialGradient id="gDense" cx="88%" cy="56%" r="50%"><stop offset="0%" stop-color="#f97316" stop-opacity="0.52"/><stop offset="100%" stop-color="#f97316" stop-opacity="0"/></radialGradient>
        <radialGradient id="gStress" cx="99%" cy="5%" r="52%"><stop offset="0%" stop-color="#ef4444" stop-opacity="0.62"/><stop offset="100%" stop-color="#ef4444" stop-opacity="0"/></radialGradient>
        <radialGradient id="gQpu" cx="100%" cy="0%" r="26%"><stop offset="0%" stop-color="#fb7185" stop-opacity="0.85"/><stop offset="70%" stop-color="#e11d48" stop-opacity="0.35"/><stop offset="100%" stop-color="#e11d48" stop-opacity="0"/></radialGradient>
        <filter id="phblur"><feGaussianBlur stdDeviation="4"/></filter>
        <filter id="phglow" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <style>#ph-cursor,#ph-cursor-core{transition:cx .45s cubic-bezier(.16,1,.3,1),cy .45s cubic-bezier(.16,1,.3,1)}@keyframes phpulse{0%{opacity:.15;r:14}70%{opacity:.45}100%{opacity:0;r:34}}#ph-zonepulse{transform-box:fill-box}</style>
      </defs>
      <rect width="260" height="180" fill="#07070c"/>
      <rect width="260" height="180" fill="url(#gLow)"/><rect width="260" height="180" fill="url(#gMagic)"/>
      <rect width="260" height="180" fill="url(#gSpr)"/><rect width="260" height="180" fill="url(#gGrid)"/>
      <rect width="260" height="180" fill="url(#gDense)"/><rect width="260" height="180" fill="url(#gStress)"/>
      <line x1="8" y1="172" x2="8" y2="12" stroke="rgba(255,255,255,0.16)" stroke-width="1"/><polygon points="8,8 5,15 11,15" fill="rgba(255,255,255,0.16)"/>
      <line x1="12" y1="172" x2="252" y2="172" stroke="rgba(255,255,255,0.16)" stroke-width="1"/><polygon points="256,172 249,169 249,175" fill="rgba(255,255,255,0.16)"/>
      <path d="M34 100 C82 90,108 122,152 106 S216 90,252 84" fill="none" stroke="rgba(226,232,240,0.14)" stroke-width="0.8" stroke-dasharray="4 4"/>
      <!-- three honest nested frontiers: perceived (literature) > classical-reachable (field SoTA) > real QPU nucleo -->
      <ellipse id="ph-core" cx="196" cy="60" rx="60" ry="56" fill="none" stroke="rgba(148,163,184,0.5)" stroke-width="1" stroke-dasharray="3 3"><title>Frontera percibida (literatura): high core + high magic. La mayoria resulta clasicamente tratable.</title></ellipse>
      <ellipse id="ph-field" cx="214" cy="46" rx="44" ry="42" fill="rgba(45,212,191,0.06)" stroke="rgba(56,189,166,0.6)" stroke-width="1" stroke-dasharray="4 3"><title>Alcanzable clasico (estado del arte del campo): tensor networks / Stim / CAMPS / Qiskit Aer simulan en esta zona.</title></ellipse>
      <ellipse id="ph-atlas-core" cx="227" cy="31" rx="27" ry="26" fill="rgba(225,29,72,0.2)" stroke="#fb7185" stroke-width="1.4"><title>Nucleo real (sin ruta clasica certificada bajo presupuesto): statevector Y MPS Y contraccion exceden el presupuesto (n mas alla de ~33).</title></ellipse>
      <path id="ph-qpu" d="M236 5 L256 5 L256 40 C248 36,241 24,236 5 Z" fill="url(#gQpu)" stroke="rgba(251,113,133,0.8)" stroke-width="1"><title>No certified classical route under declared budget (ESCALATE)</title></path>
      <text x="18" y="150" font-family="IBM Plex Sans" font-size="9.5" font-weight="800" fill="#34d399">Low-complexity</text><text x="18" y="160" font-family="IBM Plex Sans" font-size="7" fill="#6ee7b7" opacity="0.8">request</text>
      <text x="18" y="26" font-family="IBM Plex Sans" font-size="9.5" font-weight="800" fill="#a78bfa">Magic-heavy</text><text x="18" y="36" font-family="IBM Plex Sans" font-size="7" fill="#c4b5fd" opacity="0.8">request</text>
      <text x="78" y="86" font-family="IBM Plex Sans" font-size="9" font-weight="800" fill="#60a5fa">Grid frontier</text>
      <text x="92" y="150" font-family="IBM Plex Sans" font-size="9.5" font-weight="800" fill="#2dd4bf">Spread-heavy</text><text x="92" y="160" font-family="IBM Plex Sans" font-size="7" fill="#5eead4" opacity="0.8">request</text>
      <text id="ph-star" x="248" y="14" font-size="9" text-anchor="middle" fill="#fbbf24" filter="url(#phglow)">★</text>
      <text x="227" y="33" font-family="IBM Plex Sans" font-size="6" font-weight="800" fill="#fecdd3" text-anchor="middle">QPU</text>
      <text x="150" y="112" font-family="IBM Plex Sans" font-size="5.5" font-weight="700" fill="rgba(148,163,184,0.85)">frontera percibida (lit.)</text>
      <text x="172" y="90" font-family="IBM Plex Sans" font-size="5.5" font-weight="700" fill="rgba(56,189,166,0.95)">alcanzable clásico (campo)</text>
      <text x="13" y="92" font-family="IBM Plex Sans" font-size="8" fill="rgba(255,255,255,0.3)">magic ↑</text>
      <text x="146" y="168" font-family="IBM Plex Sans" font-size="8" fill="rgba(255,255,255,0.3)">spread / entangle (log) →</text>
      <text id="ph-reclaimed" x="14" y="12" font-family="IBM Plex Sans" font-size="7" font-weight="800" fill="#86efac" opacity="0.92"></text>
      <rect id="ph-noise" x="130" y="0" width="130" height="90" fill="#f87171" opacity="0"><title>noise horizon</title></rect>
      <text id="ph-noise-lbl" x="196" y="46" font-family="IBM Plex Sans" font-size="7" fill="#fecaca" text-anchor="middle" opacity="0">noise</text>
      <path id="ph-run" fill="none" stroke="#fde68a" stroke-width="1.4" stroke-linecap="round" opacity="0.85" filter="url(#phglow)"/>
      <circle id="ph-zonepulse" cx="32" cy="155" r="14" fill="none" stroke="#fde68a" stroke-width="1.5" opacity="0"/>
      <g id="ph-trail"></g><g id="ph-dots"></g>
      <circle id="ph-cursor" cx="32" cy="155" r="5" fill="white" opacity="0.9" filter="url(#phblur)"/>
      <circle id="ph-cursor-core" cx="32" cy="155" r="2.6" fill="white" filter="url(#phglow)"/>
      </svg>
      <div id=research3d class=research3d><div id=cube3d class=cube3d onpointerdown="cubeDragStart(event)" onpointerenter="_cubeHover=true" onpointerleave="_cubeHover=false"><div class="cube-axis m">Magic ↑</div><div class="cube-axis s">Spread →</div><div class="cube-axis c">Interaction density ↗</div><div id=cube-dots></div></div><div class=cube-ctrl><span></span><button onclick="cubeRotate(0,-12)" title="Rotate up">↑</button><span></span><button onclick="cubeRotate(-14,0)" title="Rotate left">←</button><button onclick="cubeReset()" title="Reset view">•</button><button onclick="cubeRotate(14,0)" title="Rotate right">→</button><span></span><button onclick="cubeRotate(0,12)" title="Rotate down">↓</button><span></span></div><div id=cube-readout class=cube-readout></div><div class=frontier-note>3D research view: X spread, Y magic, Z interaction density. Drag or use arrows. Points are circuit-family requests, not outcomes.</div></div>
      <div class=phint data-i18n=phint>${EN?'Gold ring = perceived hardness frontier (literature). Red core = the frontier with no certified classical route under budget — much smaller; the gap is territory Atlas IDENTIFIES as classically reachable with existing methods (it does NOT extend the classical frontier — it triages which side of it a circuit is on). The cursor lands by MEASURED outcome, so it enters the red core only when every classical route truly fails.':'Anillo dorado = frontera de dureza percibida (literatura). Nucleo rojo = frontera QPU real de Atlas — mucho menor; la brecha es territorio que Atlas IDENTIFICA como alcanzable clasicamente con metodos existentes (NO amplia la frontera clasica — solo hace triage de que lado de ella esta un circuito). El cursor cae por el resultado MEDIDO, asi que entra al nucleo rojo solo si toda ruta clasica realmente falla.'}</div>
      <div class=bench-bar><span class=bench-k>${EN?'Measured benchmark':'Benchmark medido'}</span><span class=bench-v><b>2517</b> ${EN?'certified':'certificados'} · 0 ${EN?'false-alarm':'falsa-alarma'} · ${EN?'false-safety':'falsa-seguridad'} <b>1/25</b> ${EN?'on checkable-hard cases (4%)':'en casos duros verificables (4%)'} · ${EN?'genuinely-hard (escalate) regime UNMEASURED — no classical ground truth':'regimen cuantico-duro (escalate) NO MEDIDO — sin ground-truth clasico'}</span><div class=bench-track><div class=bench-fill></div></div></div>
    </div><div class=landscape-side>
      <div><div class=density-bar></div><div class=density-labels><span>line</span><span>grid</span><span>dense core</span></div></div>
      <div class=phase-legend>
        <div class=phase-pill style="border-left:3px solid #94a3b8"><b>${EN?'Perceived frontier (literature)':'Frontera percibida (literatura)'}</b>${EN?'high #T + high entanglement = assumed hard':'alto #T + alto entrelazamiento = se asume duro'}</div>
        <div class=phase-pill style="border-left:3px solid #2dd4bf"><b>${EN?'Classically reachable (field SoTA)':'Alcanzable clásico (campo)'}</b>${EN?'tensor networks · Stim · CAMPS · Qiskit Aer simulate here':'tensor networks · Stim · CAMPS · Qiskit Aer simulan aquí'}</div>
        <div class=phase-pill style="border-left:3px solid #fb7185"><b>${EN?'Real core (no certified classical route)':'Núcleo real (sin ruta clásica certificada)'}</b>${EN?'statevector AND MPS AND contraction all exceed budget (n≳33)':'statevector Y MPS Y contracción exceden presupuesto (n≳33)'}</div>
        <div class=phase-pill style="border-left:3px solid #fff"><b>${EN?'● your circuit · ★ fixed frontier':'● tu circuito · ★ frontera (fija)'}</b>${EN?'the glowing dot is the analyzed circuit; the star is a fixed marker, not your circuit':'el punto brillante es el circuito analizado; la estrella es un marcador fijo, no tu circuito'}</div>
      </div>
      <div class=landscape-note style="border-color:rgba(99,102,241,.3);background:rgba(99,102,241,.06)"><b>Atlas ≠ ${EN?'new simulation power':'nuevo poder de simulación'}.</b> ${EN?'The classical frontier is the field achievement. The Atlas edge is the pre-flight triage on top: failure-mode-aware route adjudication + calibrated confidence (an error detector) + a non-circular measured benchmark.':'La frontera clásica es logro del campo. La orilla de Atlas es el triage pre-flight encima: adjudicación de ruta consciente de modos de fallo + confianza calibrada (detector de errores) + benchmark medido no-circular.'}</div>
      <div class=landscape-note>${EN?'Click the map to open the full analysis of that point.':'Pica el mapa para abrir el análisis completo de ese punto.'}</div>
    </div></div></section>`;
}
function ensureGenExplorer(){   // V2 fix: el mapa vive en diag-explorer (Explore); el slot del editor queda vacío para no duplicar #phase
  var slot=$('gen-explorer-slot');if(slot)slot.innerHTML='';
}
function resetDiagnostics(){clearTimeout(window._t);window.lastAtlas=null;trail=[];var EN=LANG==='en';if(typeof updateStepper==='function')setTimeout(updateStepper,0);
  var ps=$('pSummary'),pr=$('pResultado'),pl=$('pLog'),m=$('metrics'),st=$('st'),br=$('bResultado'),bq=$('bQASM'),pq=$('pQASM'),tg=$('decision-toggle'),p=$('decision-panel');
  if(ps){ps.innerHTML='<div class=diag-grid><div class=diag-primary><div class=empty>'+(EN?'Analyze a circuit to see its diagnostic.':'Analiza un circuito para ver su diagnostico.')+'</div></div><div class=diag-explorer>'+designExplorerHTML()+'</div></div>';if($('phase')){renderPhaseDots();phaseMode(phaseView||'2d');}}
  if(pr)pr.innerHTML='<div class=empty>'+(EN?'The circuit diagram will appear here.':'El diagrama del circuito aparecera aqui.')+'</div>';
  if(pl)pl.innerHTML='<div class=log id=logbody>'+(EN?'waiting...':'esperando...')+'</div>';
  if(pq)pq.innerHTML='<div class=empty>'+(EN?'Generated QASM will appear here.':'El QASM generado aparecera aqui.')+'</div>';
  if(m)m.innerHTML='';if(br)br.style.display='none';if(bq)bq.style.display='none';if(st)st.innerHTML='&#9679; '+(EN?'Ready':'Listo');
  if(tg){tg.classList.remove('has-result');tg.setAttribute('aria-expanded','false');}if(p)p.classList.remove('open');
  if(typeof buildDecisionPanel==='function')buildDecisionPanel();
  movePhaseCursor(0,'2^0','2^0');}
function setq(t){$('qasm').value=t;onInput();clearTimeout(window._t);if((t||'').trim())analyze();else resetDiagnostics();}
function restoreAnalyzeButton(ab){if(!ab)return;ab.disabled=false;ab.removeAttribute('aria-busy');ab.classList.remove('busy');
  ab.innerHTML=ab._html||('&#9654; <span data-i18n=btnAnalyze>'+(LANG==='en'?'Analyze':'Analizar')+'</span>');delete ab._html;}
function syncScroll(){var q=$('qasm');$('lines').scrollTop=q.scrollTop;var h=$('qasm-hl');if(h){h.scrollTop=q.scrollTop;h.scrollLeft=q.scrollLeft;}}
var _HLCL={h:1,x:1,y:1,z:1,s:1,sdg:1,sdag:1,cx:1,cnot:1,cz:1,swap:1,cy:1,ch:1,id:1},_HLMG={t:1,tdg:1,tdag:1,ccx:1,toffoli:1},_HLME={measure:1},_HLDIR={openqasm:1,include:1,qreg:1,creg:1,gate:1,barrier:1,if:1,opaque:1};
function _hlEsc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function highlightQasm(){var h=$('qasm-hl');if(!h)return;var v=$('qasm').value;
  var out=v.split('\n').map(function(line){
    if(/^\s*\/\//.test(line))return '<span class=hl-com>'+_hlEsc(line)+'</span>';
    var m=line.match(/^(\s*)([A-Za-z_][\w]*)/);
    if(m){var w=m[2],lw=w.toLowerCase(),rest=_hlEsc(line.slice(m[0].length)),cls=null;
      if(_HLDIR[lw])cls='hl-dir';else if(_HLCL[lw])cls='hl-cliff';else if(_HLMG[lw])cls='hl-magic';else if(_HLME[lw])cls='hl-meas';
      if(cls)return _hlEsc(m[1])+'<span class='+cls+'>'+_hlEsc(w)+'</span>'+rest;}
    return _hlEsc(line);
  }).join('\n');
  h.innerHTML=out+'\n';}   // newline final -> el alto de la última línea coincide con el textarea
function onInput(){let v=$('qasm').value,L=v.split('\n').length;let s='';for(let i=1;i<=L;i++)s+=i+'\n';$('lines').textContent=s;highlightQasm();syncScroll();
  let m=v.match(/qreg\s+\w+\s*\[\s*(\d+)/)||v.match(/qubit\s*\[\s*(\d+)/);$('nq').textContent='n='+(m?m[1]:0)+' qubits';
  $('chars').textContent=v.length+' chars';clearTimeout(window._t);if(v.trim())window._t=setTimeout(analyze,450);else resetDiagnostics();
  if(typeof updateStepper==='function')updateStepper();}
function curpos(){let t=$('qasm'),p=t.value.substr(0,t.selectionStart).split('\n');$('pos').textContent='Ln '+p.length+', Col '+(p[p.length-1].length+1)}
function mode(m){curMode=m;$('tabDx').classList.toggle('active',m=='dx');$('tabGen').classList.toggle('active',m=='gen');
  $('tabDx').setAttribute('aria-selected',m=='dx');$('tabGen').setAttribute('aria-selected',m=='gen');
  var main=document.querySelector('main.main');if(main)main.classList.toggle('gen-mode',m=='gen');
  $('genpanel').classList.toggle('on',m=='gen');$('qasm').style.display=m=='gen'?'none':'';$('lines').style.display=m=='gen'?'none':'';
  var slot=$('gen-explorer-slot');if(slot)slot.innerHTML='';   // V2 fix: el mapa ya no se mueve al editor; vive en diag-explorer (Explore)
  if(m!=='gen'){if(window.lastAtlas)showResult(window.lastAtlas);else resetDiagnostics();}}
// V2-2: workspaces — cada uno lidera su contenido vía body.ws-*; sin reconstruir el DOM
var curWs='author';
function setWorkspace(ws){if(['author','triage','explore'].indexOf(ws)<0)ws='author';curWs=ws;
  document.body.classList.remove('ws-author','ws-triage','ws-explore');document.body.classList.add('ws-'+ws);
  [['author','wsAuthor'],['triage','wsTriage'],['explore','wsExplore']].forEach(function(p){var b=$(p[1]);if(b){b.classList.toggle('active',p[0]===ws);b.setAttribute('aria-selected',p[0]===ws?'true':'false');}});
  var sub=$('authorSub');if(sub)sub.style.display=(ws==='author')?'':'none';
  if(ws==='explore'){try{if(typeof renderPhaseDots==='function')renderPhaseDots();if(typeof phaseMode==='function')phaseMode(phaseView||'2d');}catch(e){}}
  updateStepper();}
// V2-3: stepper — refleja el loop Definir→Explorar→Medir→Decidir según el estado real
function updateStepper(){var o=window.lastAtlas,EN=LANG==='en';
  var hasCircuit=((($('qasm')&&$('qasm').value)||'').trim()).length>10;
  ['step1','step2','step3','step4'].forEach(function(id){var el=$(id);if(el)el.classList.remove('active','done');});
  if(hasCircuit){var e1=$('step1');if(e1)e1.classList.add('done');}
  if(o){var e2=$('step2'),e3=$('step3');if(e2)e2.classList.add('done');if(e3)e3.classList.add('done');}
  var wsMap={author:'step1',explore:'step2',triage:'step3'},act=$(wsMap[curWs]||'step1');
  if(act){act.classList.remove('done');act.classList.add('active');}
  var route=(o&&o.route_adjudication&&o.route_adjudication.route)||'';
  function sub(id,t){var e=$(id);if(e)e.textContent=t;}
  sub('step1sub',hasCircuit?(EN?'circuit ready':'circuito listo'):(EN?'write / generate':'escribe / genera'));
  sub('step2sub',o?(EN?'mapped':'mapeado'):'—');
  sub('step3sub',o?(EN?'measured':'medido'):(EN?'analyze':'analiza'));
  sub('step4sub',o?('→ '+(route||(EN?'decide':'decidir'))):(EN?'pending':'pendiente'));}
function otab(t){['Resultado','Log'].forEach(x=>{var o=$('o'+x),p=$('p'+x);if(o)o.classList.toggle('active',x==t);if(p)p.classList.toggle('on',x==t)})}
function toggleNoise(el){var b=el.closest('.noise-box');if(b)b.classList.toggle('collapsed');}
function exportQASM(){var q=($('qasm')&&$('qasm').value)||'';if(!q.trim())return;var b=new Blob([q],{type:'text/plain'});var u=URL.createObjectURL(b);var a=document.createElement('a');a.href=u;a.download='circuit.qasm';a.click();URL.revokeObjectURL(u);}
function _dl(text,name){var b=new Blob([text],{type:'text/plain'});var u=URL.createObjectURL(b);var a=document.createElement('a');a.href=u;a.download=name;a.click();URL.revokeObjectURL(u);}
async function exportQIR(){var q=($('qasm')&&$('qasm').value)||'';if(!q.trim())return;       // QIR (LLVM IR, .ll) via backend
  try{var o=await post('/api/qir',{qasm:q});if(o&&o.qir){_dl(o.qir,'circuit.ll');
    var rt=o.roundtrip||{};var sm=rt.structural_match,se=rt.semantic_equivalence;   // P1-3 audit: mostrar el certificado de equivalencia, no solo descargar
    var msg;if(sm===true&&(se===true||(typeof se==='string'&&se.indexOf('structural')===0)))msg='&#9679; QIR exportado (n='+(o.n||'?')+') · round-trip OK: estructura ✓'+(se===true?' + unitario exacto ✓ (n≤7)':' (n>7: solo estructural)');
    else if(sm===false)msg='&#9679; QIR exportado PERO round-trip FALLA (estructura ✗) — el encoder no es fiel a este circuito';
    else msg='&#9679; QIR exportado (n='+(o.n||'?')+')';
    $('st').innerHTML=msg;}
    else if(o&&o.error)$('st').innerHTML='&#9679; '+o.error;}catch(e){}}
function _hash32(s){var h=2166136261>>>0;for(var i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return ('00000000'+(h>>>0).toString(16)).slice(-8);}
function exportReport(){var o=window.lastAtlas;if(!o)return;var v=atlasVerdict(o),c=o.costs_log2||{};
  var q=o.qasm_in||(($('qasm')&&$('qasm').value)||''),gt=o.ground_truth&&o.ground_truth.methods?o.ground_truth.methods:{},r=atlasRecommendation(o,v),x=explainWhy(o,v);
  var lines=['Atlas Quantum Compute Triage Report','','Circuit:','  hash32: '+_hash32(q),'  qubits: '+(o.n||'n/a'),'  gates: '+(o.circuit&&o.circuit.total!=null?o.circuit.total:'n/a'),'','Pre-flight triage result:','  '+v.question+' '+v.answer,'  technical diagnostic: '+(o.verdict||''),'  scope: diagnostic support, not a proof of universal simulability or quantum advantage','','Heuristic diagnostic index:','  index: '+v.score+'/100','  band: '+v.band,'  estimated memory proxy: '+v.memory,'  confidence: '+v.confidence,'  contributors: base '+v.parts.base+', magic '+v.parts.magic+', treewidth '+v.parts.treewidth+', MPS '+v.parts.mps+', spread '+v.parts.spread+', clamp '+v.parts.clamp,'','Recommended compute path:','  '+r.title,'  '+r.items.join('\\n  '),'','Reason:','  '+v.reason,'  observed: '+x.observed,'  threshold: '+x.threshold,'  interpretation: '+x.detail,'','Multi-method consistency:','  Stim: '+(gt.stim?'available':'n/a'),'  quimb: '+(gt.quimb?'available':'n/a'),'  cotengra: '+(gt.cotengra?'available':'n/a'),'  Pauli propagation: '+(gt.pauli?'available':'n/a'),'','Scientific scope:','  SUPPORTED: operational compute triage','  SUPPORTED: classical simulability diagnostics for this circuit','  LIMITED: simulation cost is a proxy/estimate, not a universal prediction','  NOT CLAIMED: quantum advantage identification','  NOT CLAIMED: impossible-circuit proof','','Generated: '+new Date().toISOString(),'','Method: magic estimator -> Pauli spread -> tensor metrics -> multi-method consistency -> compute triage recommendation'];
  var ct=o.certificate;                                  // A*: append the auditable certificate
  if(ct){var cf=ct.confidence||{},pr=ct.provenance||{},w=ct.witnesses||{},fs=ct.false_safety_risk||{};
    var more=['','=== AUDITABLE CERTIFICATE (atlas_certificate/v1) ===',
      'route: '+ct.route,
      'witness: '+((ct.witness||{}).reads||''),
      'confidence tier ['+(cf.tier||'?')+']: '+(cf.reads||''),
      'false-safety risk ['+(fs.band||'n/a')+' '+(fs.risk!=null?fs.risk:'')+'] (route-independent): '+(fs.reads||''),
      '','witnesses (what each number IS / IS NOT):',
      '  spread: '+((w.spread||{}).is||'')+' | '+((w.spread||{}).is_not||''),
      '  memory: '+((w.memory||{}).is||'')+' | exact statevector bytes='+((w.memory||{}).exact_statevector_bytes_complex128),
      '  treewidth: '+((w.treewidth||{}).is||'')+' | '+((w.treewidth||{}).is_not||''),
      '','provenance:',
      '  qasm_sha256: '+(pr.qasm_sha256||''),
      '  n_qubits: '+pr.n_qubits+'  t_count: '+pr.t_count,
      '  engine_versions: '+JSON.stringify(pr.engine_versions||{}),
      '  exactness: '+JSON.stringify(pr.exactness||{}),
      '','hardware reachability ['+((ct.hardware||{}).backend||'n/a')+']: '+((ct.hardware||{}).applies?((ct.hardware.reachable?'REACHABLE':'NOT reachable')+' — '+(ct.hardware.text||'')):'n/a (classical route)'),
      '','impossibility: '+((ct.impossibility||{}).absolute||''),
      'caveats:'].concat((ct.caveats||[]).map(function(c){return '  • '+c;}));
    lines=lines.concat(more);}
  try{_dl(lines.join('\n'),'atlas_simulatability_diagnostics_'+Date.now()+'.txt');toast(LANG==='en'?'✓ Report downloaded':'✓ Reporte descargado');}catch(e){toast(LANG==='en'?'✗ Export failed':'✗ Falló la exportación',true);}}
var _toastT=null;
function toast(msg,err){var t=document.getElementById('atlas-toast');if(!t)return;t.textContent=msg;t.classList.toggle('err',!!err);t.classList.add('show');clearTimeout(_toastT);_toastT=setTimeout(function(){t.classList.remove('show');},2400);}
// ===== RENDER del CIRCUITO (SVG): lineas de qubit + cajas de compuerta + CNOT/CZ/SWAP =====
function drawCircuit(n,cd,target){
  var pane=$(target||'pCircuito');if(!pane)return;
  if(!cd||!cd.gates||!cd.gates.length){pane.innerHTML='<div class=empty>'+(LANG==='en'?'No gates to display.':'Sin compuertas que mostrar.')+'</div>';return;}
  var gates=cd.gates,col=[];for(var q=0;q<n;q++)col[q]=0;var placed=[];
  for(var i=0;i<gates.length;i++){var g=gates[i],qs=g.slice(1),c=0;
    for(var k=0;k<qs.length;k++)c=Math.max(c,col[qs[k]]);
    for(var k=0;k<qs.length;k++)col[qs[k]]=c+1;placed.push({op:g[0],qs:qs,col:c});}
  var ncol=0;for(var q=0;q<n;q++)ncol=Math.max(ncol,col[q]);
  var RH=(n<=8)?38:Math.min(38,Math.floor(300/n));   // alto de fila: n>8 se comprime para caber en ~300px
  var hb=Math.max(7,Math.min(13,Math.floor(RH/2)-2)),fs=Math.max(7,Math.min(10.5,RH*0.28));  // caja/fuente proporcionales
  var qr=Math.min(9,hb),cr=Math.max(2.5,Math.min(3.5,hb*0.5)),xm=Math.max(3,hb*0.45),top=16;  // radios/marcas escalados
  var ql=Math.min(11,Math.max(7,RH*0.5));            // tamano de la etiqueta q[i]
  var W=70+ncol*40+20,Hh=top+n*RH+10;
  var COL={h:'#3b82f6',t:'#8b5cf6',tdg:'#8b5cf6',s:'#14b8a6',sdg:'#14b8a6',x:'#ef4444',y:'#ef4444',z:'#64748b',rz:'#a78bfa',sx:'#0ea5e9'};
  var LBL={h:'H',t:'T',tdg:'T†',s:'S',sdg:'S†',x:'X',y:'Y',z:'Z',rz:'Rz',sx:'√X'};
  function X(c){return 70+c*40;}function Y(q){return top+RH/2+q*RH;}
  var s='<svg viewBox="0 0 '+W+' '+Hh+'" width="'+W+'" height="'+Hh+'" style="background:#0a0a0e;border-radius:8px;display:block">';   // tamano NATURAL (no width:100%): evita que el SVG se infle al estirarse; el contenedor hace scroll
  for(var q=0;q<n;q++){s+='<text x="8" y="'+(Y(q)+ql*0.35)+'" fill="#94a3b8" font-family="monospace" font-size="'+ql.toFixed(1)+'">q['+q+']</text>';
    s+='<line x1="44" y1="'+Y(q)+'" x2="'+(W-10)+'" y2="'+Y(q)+'" stroke="rgba(255,255,255,0.18)" stroke-width="1"/>';}
  for(var i=0;i<placed.length;i++){var p=placed[i],x=X(p.col);
    if(p.qs.length===2){var ya=Y(p.qs[0]),yb=Y(p.qs[1]);
      s+='<line x1="'+x+'" y1="'+Math.min(ya,yb)+'" x2="'+x+'" y2="'+Math.max(ya,yb)+'" stroke="#cbd5e1" stroke-width="1.5"/>';
      if(p.op==='cx'){s+='<circle cx="'+x+'" cy="'+ya+'" r="'+cr+'" fill="#cbd5e1"/><circle cx="'+x+'" cy="'+yb+'" r="'+qr+'" fill="#0a0a0e" stroke="#cbd5e1" stroke-width="1.5"/><line x1="'+(x-qr)+'" y1="'+yb+'" x2="'+(x+qr)+'" y2="'+yb+'" stroke="#cbd5e1" stroke-width="1.5"/><line x1="'+x+'" y1="'+(yb-qr)+'" x2="'+x+'" y2="'+(yb+qr)+'" stroke="#cbd5e1" stroke-width="1.5"/>';}
      else if(p.op==='cz'){s+='<circle cx="'+x+'" cy="'+ya+'" r="'+cr+'" fill="#cbd5e1"/><circle cx="'+x+'" cy="'+yb+'" r="'+cr+'" fill="#cbd5e1"/>';}
      else{[ya,yb].forEach(function(y){s+='<line x1="'+(x-xm)+'" y1="'+(y-xm)+'" x2="'+(x+xm)+'" y2="'+(y+xm)+'" stroke="#cbd5e1" stroke-width="1.5"/><line x1="'+(x-xm)+'" y1="'+(y+xm)+'" x2="'+(x+xm)+'" y2="'+(y-xm)+'" stroke="#cbd5e1" stroke-width="1.5"/>';});}
    }else{var y=Y(p.qs[0]),cc=COL[p.op]||'#475569',l=LBL[p.op]||p.op;
      s+='<rect x="'+(x-hb)+'" y="'+(y-hb)+'" width="'+(2*hb)+'" height="'+(2*hb)+'" rx="4" fill="'+cc+'"/>';
      s+='<text x="'+x+'" y="'+(y+fs*0.35)+'" fill="#fff" font-family="monospace" font-size="'+fs.toFixed(1)+'" font-weight="700" text-anchor="middle">'+l+'</text>';}}
  s+='<line class="ph-play" x1="70" y1="14" x2="70" y2="'+(Hh-6)+'" stroke="#fbbf24" stroke-width="2" opacity="0"/>';
  s+='</svg>';
  if(cd.truncated)s+='<div style="color:#f59e0b;font-size:11px;margin-top:6px">'+(LANG==='en'?'Showing first '+gates.length+' of '+cd.total+' primitives. ':'Mostrando los primeros '+gates.length+' de '+cd.total+' primitivos. ')+'<button class="playbtn" style="vertical-align:middle" onclick="loadFullCircuit()">'+(LANG==='en'?'Show all →':'Ver todos →')+'</button></div>';
  // en el tab 'Circuito' los controles de audio tambien deben estar accesibles (no solo en Resultado)
  var ctl=(target==='pCircuito')?('<div class=circ-head style="margin-top:0"><button class=playbtn onclick="playLast()">'+(LANG==='en'?'♪ Play':'♪ Reproducir')+'</button><button class=playbtn onclick="exportLast()">⤓ WAV</button></div>'):'';
  pane.innerHTML=ctl+'<div style="overflow-x:auto">'+s+'</div>';}
// "Ver todos": segundo POST que trae TODOS los primitivos sin re-analizar; solo redibuja el circuito.
async function loadFullCircuit(){
  var q=(window.lastAtlas&&window.lastAtlas.qasm_in)||($('qasm')&&$('qasm').value)||'';
  if(!q.trim())return;
  var btns=document.querySelectorAll('#circ-inline button[onclick="loadFullCircuit()"],#pCircuito button[onclick="loadFullCircuit()"]');
  btns.forEach(function(b){b.disabled=true;b.textContent=(LANG==='en'?'Loading…':'Cargando…');});
  try{
    var o=await post('/api/diagnose',{qasm:q,full_circuit:true});
    if(o&&o.circuit){
      if(window.lastAtlas)window.lastAtlas.circuit=o.circuit;
      var nn=o.n||(window.lastAtlas&&window.lastAtlas.n)||8;
      drawCircuit(nn,o.circuit,'circ-inline');drawCircuit(nn,o.circuit,'pCircuito');updLoops();
    }
  }catch(e){btns.forEach(function(b){b.disabled=false;b.textContent=(LANG==='en'?'Show all →':'Ver todos →');});}
}
// ===== JUST FOR FUN: el circuito TOCA una cancion (Web Audio). Qubit->nota (pentatonica), columna->tiempo,
// compuerta->timbre. T (magia)=quinta brillante; CX/CZ=dos qubits en armonia. =====
var AC=null,PLAYING=false;
function _freq(q){var penta=[0,2,4,7,9],midi=48+Math.floor(q/5)*12+penta[q%5];return 440*Math.pow(2,(midi-69)/12);}
// sintesis parametrizada por CONTEXTO (ctx) -> sirve al vivo (AudioContext) y al export (OfflineAudioContext)
function _blip(ctx,t,f,dur,type,gain,detune,out){var o=ctx.createOscillator(),g=ctx.createGain();o.type=type;o.frequency.value=f;if(detune)o.detune.value=detune;
  g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(gain,t+0.012);g.gain.exponentialRampToValueAtTime(0.0001,t+dur);
  o.connect(g);g.connect(out||ctx.destination);o.start(t);o.stop(t+dur+0.02);}
function _noiseBuf(ctx){if(ctx._nb)return ctx._nb;var b=ctx.createBuffer(1,Math.floor(ctx.sampleRate*0.6),ctx.sampleRate),d=b.getChannelData(0);for(var i=0;i<d.length;i++)d[i]=Math.random()*2-1;ctx._nb=b;return b;}
function _hiss(ctx,t,dur,gain,out){var s=ctx.createBufferSource();s.buffer=_noiseBuf(ctx);var f=ctx.createBiquadFilter();f.type='bandpass';f.frequency.value=800+Math.random()*1600;f.Q.value=1.2;var g=ctx.createGain();
  g.gain.setValueAtTime(0,t);g.gain.linearRampToValueAtTime(gain,t+0.01);g.gain.exponentialRampToValueAtTime(0.0001,t+dur);s.connect(f);f.connect(g);g.connect(out||ctx.destination);s.start(t);s.stop(t+dur+0.02);}
// --- textura sonora anclada a la FÍSICA del circuito (magia/entrelazado/treewidth/ruido) ---
function _reverbIR(ctx,sec,decay){var len=Math.max(1,Math.floor(ctx.sampleRate*sec)),b=ctx.createBuffer(2,len,ctx.sampleRate);for(var c=0;c<2;c++){var d=b.getChannelData(c);for(var i=0;i<len;i++)d[i]=(Math.random()*2-1)*Math.pow(1-i/len,decay);}return b;}
function _shaper(amount){var nn=1024,c=new Float32Array(nn),k=amount*60;for(var i=0;i<nn;i++){var x=i*2/nn-1;c[i]=(1+k)*x/(1+k*Math.abs(x));}return c;}
function _feats(n,cd){var t=0,g=cd.gates;for(var i=0;i<g.length;i++)if(g[i][0]==='t'||g[i][0]==='tdg')t++;   // magia=densidad T; entrelazado=MPS bond log2; tw=treewidth log2 (del análisis del server)
  var c=(window.lastAtlas&&window.lastAtlas.costs_log2)||{};var mps=+c['MPS(entangle)']||1,tw=+c['contraction(treewidth)']||0;
  return {magic:g.length?t/g.length:0,ent:Math.min(1,mps/10),tw:Math.min(1,tw/Math.max(4,n))};}
function _master(ctx,F,dur,t0){var inp=ctx.createGain();
  var shp=ctx.createWaveShaper();shp.curve=_shaper(0.15+0.85*F.magic);                       // magia -> drive/inarmonicidad
  var lp=ctx.createBiquadFilter();lp.type='lowpass';lp.frequency.setValueAtTime(7000-2200*F.magic,t0);lp.Q.value=0.7;
  var dry=ctx.createGain();dry.gain.value=0.78;
  var conv=ctx.createConvolver();conv.buffer=_reverbIR(ctx,1.0+2.6*F.ent,2.2);               // entrelazado -> cola de reverb (espacio)
  var wet=ctx.createGain();wet.gain.value=0.10+0.55*F.ent;
  var out=ctx.createGain();out.gain.value=0.85;
  inp.connect(shp);shp.connect(lp);lp.connect(dry);lp.connect(conv);conv.connect(wet);dry.connect(out);wet.connect(out);out.connect(ctx.destination);
  return {input:inp,lp:lp};}
function _drone(ctx,n,F,t0,dur,out){if(F.tw<0.06)return;var base=_freq(0)/2,voices=1+Math.round(F.tw*4);  // treewidth -> pad de fondo (riqueza del 'costo')
  for(var v=0;v<voices;v++){var o=ctx.createOscillator(),g=ctx.createGain();o.type='sawtooth';o.frequency.value=base*(1+v*0.5);o.detune.value=(v-voices/2)*9*(1+F.magic);
    g.gain.setValueAtTime(0,t0);g.gain.linearRampToValueAtTime(0.022*F.tw,t0+0.9);g.gain.setValueAtTime(0.022*F.tw,t0+Math.max(1,dur-0.9));g.gain.linearRampToValueAtTime(0.0001,t0+dur);
    o.connect(g);g.connect(out);o.start(t0);o.stop(t0+dur+0.05);}}
function _columns(n,gates){var col=[];for(var q=0;q<n;q++)col[q]=0;var placed=[];
  for(var i=0;i<gates.length;i++){var g=gates[i],qs=g.slice(1),c=0;for(var k=0;k<qs.length;k++)c=Math.max(c,col[qs[k]]);for(var k=0;k<qs.length;k++)col[qs[k]]=c+1;placed.push({op:g[0],qs:qs,col:c});}
  var ncol=0;for(var q=0;q<n;q++)ncol=Math.max(ncol,col[q]);return {placed:placed,ncol:ncol};}
function _schedule(ctx,n,cd,np,t0){       // agenda toda la cancion en ctx; devuelve {ncol,dur,k2qTot}
  var pc=_columns(n,cd.gates),placed=pc.placed,ncol=pc.ncol,k2q=0;
  var F=_feats(n,cd),step=0.20-0.05*F.magic,dur=(ncol+1)*step;   // magia acelera el ritmo (rompe el metronomo)
  var M=_master(ctx,F,dur,t0),out=M.input;_drone(ctx,n,F,t0,dur,out);
  var fOpen=7000-2200*F.magic,fEnd=Math.max(480,fOpen*Math.pow(1-Math.min(0.92,np*8+F.ent*0.25),3));
  M.lp.frequency.linearRampToValueAtTime(fEnd,t0+dur);          // momento/ruido: el lowpass se cierra -> decoherencia audible
  for(var i=0;i<placed.length;i++){var P=placed[i];
    var swing=(P.col%2)?0.014:0,t=t0+P.col*step+swing,q=P.qs[0],f=_freq(q);
    if(P.qs.length===2)k2q++;
    var surv=Math.pow(1-np,k2q);
    if(Math.random()>=surv){_hiss(ctx,t,0.18,0.04*(1-surv)+0.015,out);
      if(Math.random()<0.5)_blip(ctx,t,f,0.16,'sine',0.04,(Math.random()*2-1)*150,out);continue;}
    var dt=(1-surv)*(Math.random()*2-1)*70+F.magic*(Math.random()*2-1)*26,gm=0.6+0.4*surv;
    if(P.op==='h')_blip(ctx,t,f,0.42,'sine',0.20*gm,dt,out);
    else if(P.op==='t'||P.op==='tdg'){_blip(ctx,t,f,0.5,'triangle',0.16*gm,dt,out);_blip(ctx,t,f*1.5,0.42,'sine',0.07*gm,dt,out);
      _blip(ctx,t,f*(1.61+0.5*F.magic),0.5,'sine',0.02+0.06*F.magic*gm,dt,out);}   // parcial INARMONICO ~ magia (no-estabilizador)
    else if(P.op==='s'||P.op==='sdg')_blip(ctx,t,f,0.32,'sine',0.13*gm,dt,out);
    else if(P.op==='cx'||P.op==='cz'||P.op==='swap'){var f0=_freq(P.qs[0]),f1=_freq(P.qs[1]);_blip(ctx,t,f0,0.42,'sine',0.13*gm,dt,out);_blip(ctx,t,f1,0.46,'sine',0.17*gm,dt,out);
      if(F.ent>0.18)_blip(ctx,t,Math.abs(f1-f0)+60,0.3,'sine',0.05*gm*F.ent,dt,out);}   // tono de ACOPLAMIENTO (diferencia) ~ entrelazado
    else if(P.op==='x'||P.op==='y'||P.op==='z')_blip(ctx,t,f,0.2,'square',0.10*gm,dt,out);
    else if(P.op==='rz')_blip(ctx,t,f,0.3,'sawtooth',0.09*gm,dt,out);}
  return {ncol:ncol,dur:dur,k2qTot:k2q};}
function _noiseRate(){var e=document.getElementById('noise-p');return e?(+e.value||0)/1000:0;}
function _loops(){var e=document.getElementById('audio-loops');return Math.max(1,Math.min(64,+(e&&e.value)||1));}
function updLoops(){var o=window.lastAtlas,s=document.getElementById('loopsec');if(!s)return;
  if(o&&o.circuit){var pc=_columns(o.n||8,o.circuit.gates),sec=(pc.ncol+1)*0.19*_loops();s.textContent='≈ '+sec.toFixed(1)+'s';}}
function playCircuit(n,cd){
  if(PLAYING||!cd||!cd.gates||!cd.gates.length)return;
  if(!AC)AC=new (window.AudioContext||window.webkitAudioContext)();
  if(AC.state==='suspended')AC.resume();
  var np=_noiseRate(),loops=_loops(),t0=AC.currentTime+0.06;
  var r=_schedule(AC,n,cd,np,t0),ncol=r.ncol,dur1=r.dur,k2qTot=r.k2qTot;
  for(var L=1;L<loops;L++)_schedule(AC,n,cd,np,t0+L*dur1);   // repetir la cancion 'loops' veces
  var total=dur1*loops;PLAYING=true;
  var line=document.querySelector('#circ-inline .ph-play');if(line)line.setAttribute('opacity','0.9');
  var x0=70,x1=70+ncol*40,start=AC.currentTime;
  (function sweep(){if(!PLAYING||!AC){return;}                 // detenido manualmente -> corta el cabezal
    var el=AC.currentTime-start;if(el>=total){if(line){line.setAttribute('opacity','0');line.setAttribute('stroke','#fbbf24');}PLAYING=false;
      var b=document.getElementById('playbtn');if(b)b.textContent=LANG==='en'?'♪ Play':'♪ Reproducir';return;}
    var e=(el/dur1)%1;                                       // posicion dentro del loop actual (el cabezal reinicia)
    if(line){var sv=Math.pow(1-np,k2qTot*e),d=1-sv;
      line.setAttribute('stroke','rgb('+Math.round(251-3*d)+','+Math.round(191-78*d)+','+Math.round(36+77*d)+')');
      line.setAttribute('x1',x0+(x1-x0)*e);line.setAttribute('x2',x0+(x1-x0)*e);}
    requestAnimationFrame(sweep);})();
  var b=document.getElementById('playbtn');if(b)b.textContent=LANG==='en'?'⏹ Stop':'⏹ Detener';}
function stopPlay(){PLAYING=false;if(AC){try{AC.close();}catch(_){}}AC=null;     // mata el audio agendado al instante
  var line=document.querySelector('#circ-inline .ph-play');if(line){line.setAttribute('opacity','0');line.setAttribute('stroke','#fbbf24');}
  var b=document.getElementById('playbtn');if(b)b.textContent=LANG==='en'?'♪ Play':'♪ Reproducir';}
function playLast(){if(PLAYING){stopPlay();return;}                              // el boton hace toggle play/stop
  if(window.lastAtlas&&window.lastAtlas.circuit)playCircuit(window.lastAtlas.n||8,window.lastAtlas.circuit);}
// EXPORTAR el sonido a WAV: render OFFLINE (sin reproducir) -> PCM 16-bit -> descarga
function _wav(buf){var ch=buf.getChannelData(0),len=ch.length,sr=buf.sampleRate,ab=new ArrayBuffer(44+len*2),dv=new DataView(ab);
  function ws(o,s){for(var i=0;i<s.length;i++)dv.setUint8(o+i,s.charCodeAt(i));}
  ws(0,'RIFF');dv.setUint32(4,36+len*2,true);ws(8,'WAVE');ws(12,'fmt ');dv.setUint32(16,16,true);dv.setUint16(20,1,true);dv.setUint16(22,1,true);
  dv.setUint32(24,sr,true);dv.setUint32(28,sr*2,true);dv.setUint16(32,2,true);dv.setUint16(34,16,true);ws(36,'data');dv.setUint32(40,len*2,true);
  var o=44;for(var i=0;i<len;i++){var s=Math.max(-1,Math.min(1,ch[i]));dv.setInt16(o,s<0?s*0x8000:s*0x7FFF,true);o+=2;}
  return new Blob([ab],{type:'audio/wav'});}
function exportCircuitAudio(n,cd){
  if(!cd||!cd.gates||!cd.gates.length)return;
  var sr=44100,step=0.20,np=_noiseRate(),loops=_loops(),pc=_columns(n,cd.gates),dur1=(pc.ncol+1)*step,total=dur1*loops+4.2;  // +cola de reverb (entrelazado) hasta ~3.6s + margen
  var OC=window.OfflineAudioContext||window.webkitOfflineAudioContext;
  if(!OC){alert(LANG==='en'?'Audio export not supported in this browser.':'Tu navegador no soporta exportar audio.');return;}
  var oc=new OC(1,Math.ceil(total*sr),sr);
  for(var L=0;L<loops;L++)_schedule(oc,n,cd,np,0.06+L*dur1);   // 'loops' repeticiones en el WAV
  var eb=document.getElementById('expbtn');if(eb)eb.textContent=LANG==='en'?'… rendering':'… renderizando';
  oc.startRendering().then(function(buf){var blob=_wav(buf),u=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=u;a.download='circuit_'+n+'q_p'+Math.round(np*1000)+'permil_'+Date.now()+'.wav';a.click();URL.revokeObjectURL(u);
    if(eb)eb.textContent=LANG==='en'?'⤓ WAV':'⤓ WAV';});}
function exportLast(){if(window.lastAtlas&&window.lastAtlas.circuit)exportCircuitAudio(window.lastAtlas.n||8,window.lastAtlas.circuit);}
function seg(g,btn,v){dials[g]=v;btn.parentNode.querySelectorAll('button').forEach(b=>b.classList.remove('on'));btn.classList.add('on')}
async function post(u,b,timeoutMs){
  // Bug#1/#9: blinda contra respuestas NO-JSON (p.ej. "stream timeout" del proxy/ingress) y
  // añade timeout de cliente con cancelación + mensaje amigable. Todos los callers leen d.error.
  var ctrl=(typeof AbortController!=='undefined')?new AbortController():null;
  var to=ctrl?setTimeout(function(){try{ctrl.abort()}catch(e){}}, timeoutMs||60000):null;
  try{
    var r=await fetch(u,{method:'POST',body:JSON.stringify(b),signal:ctrl?ctrl.signal:undefined});
    var t=await r.text();
    try{return JSON.parse(t);}
    catch(e){
      var snip=(t||'').slice(0,100).replace(/\s+/g,' ').trim();
      if(/timeout/i.test(t)||r.status===504||r.status===502)
        return {error:'El análisis tardó demasiado (timeout del servidor). Prueba un circuito más pequeño, o usa la CLI local atlas_run.py para n grande.'};
      return {error:(r.ok?'Respuesta no-JSON del servidor':'Error '+r.status)+(snip?': '+snip:'')};
    }
  }catch(e){
    if(e&&e.name==='AbortError')
      return {error:'El análisis superó '+Math.round((timeoutMs||60000)/1000)+'s y se canceló. Prueba un circuito más pequeño o la CLI local.'};
    return {error:'error de red: '+((e&&e.message)||e)};
  }finally{if(to)clearTimeout(to);}
}
function _fmtCert(c){if(!c)return 'sin certificado';if(c.error)return c.error;var w=c.witness||{},cf=c.confidence||{},dr=c.driver||{},im=c.impossibility||{},fs=c.false_safety_risk||null;var s='RUTA: '+c.route+'\n'+'WITNESS: '+(w.reads||w.claim||'')+'\n'+'CONFIANZA ['+(cf.tier||'?')+']: '+(cf.reads||'');if(fs)s+='\nRIESGO FALSA-SEGURIDAD ['+fs.band+' '+fs.risk+'] (independiente de la ruta): '+(fs.reads||'');s+='\nDRIVER: '+(dr.is||'')+' -> '+(dr.lever||'');var hw=c.hardware||null;
  if(hw&&hw.applies){s+='\nALCANZABILIDAD HW ['+(hw.backend||'')+(hw.reachable?' ✓':' ✗')+']: '+(hw.text||'');
    if(hw.depth_ceiling_realistic!=null)s+='\n  techo de profundidad REALISTA (metal real, κ̂-corregido): ~'+hw.depth_ceiling_realistic+' capas CZ  ·  1er orden (optimista): '+(hw.depth_ceiling_first_order||[])[0]+'–'+(hw.depth_ceiling_first_order||[])[1]+' capas';
    var ln=hw.learned;if(ln)s+='\n  corrección APRENDIDA (conformal, DATOS PROPIOS): '+(ln.direction||'')+'; sesgo '+Math.round(ln.bias_before*100)+'%→'+Math.round(ln.bias_after_holdout*100)+'% (held-out), banda '+Math.round(ln.coverage*100)+'% ±'+ln.conformal_band+' [κ̂='+ln.kappa_hat+'; '+(ln.caveat||'')+']';
    var rq=hw.recommended_qubits;if(rq&&rq.recommended)s+='\n  EMBEDDING sugerido (usa estos qubits): '+JSON.stringify(rq.recommended)+'  evita: '+JSON.stringify(rq.avoid);
    var hwcf=hw.calibration_freshness;if(hwcf&&hwcf.label){s+='\n  '+hwcf.label;}else if(hw.measured){s+='\n  calibración medida: '+hw.measured;}}
  s+='\nIMPOSIBILIDAD: '+(im.beyond_tracked_paradigms_reads||'')+' | '+(im.absolute||'');(c.caveats||[]).forEach(function(cv){s+='\n  • '+cv});return s;}
async function atlasCert(){var t=$('qasm'),p=$('certPanel');if(!t||!p)return;var q=t.value||'';if(!q.trim()){p.textContent='Pega un circuito OpenQASM primero.';return}p.textContent='midiendo certificado...';try{var c=await post('/api/certificate',{qasm:q});p.textContent=_fmtCert(c);}catch(e){p.textContent='error: '+e}}
async function atlasEmulate(){var t=$('qasm'),p=$('certPanel');if(!t||!p)return;var q=t.value||'';if(!q.trim()){p.textContent='Pega un circuito OpenQASM primero.';return}p.textContent='emulando ruido del device (tasas medidas, sin gastar shots)...';try{var d=await post('/api/emulate',{qasm:q});if(d.error){p.textContent=d.error;return}var emb=await post('/api/embedding',{qasm:q});var s='EMULADOR FIEL-AL-RUIDO (token-free, tasas MEDIDAS de ibm_kingston)\n';s+='n='+d.n+'  fidelidad estimada F='+d.fidelity_est+'  (n2q='+d.n2q+', n1q='+d.n1q+')\n';s+='TVD(ideal, emulado) = '+d.tvd_ideal_vs_emulated+'\n\nsalida ruidosa (top):\n';Object.keys(d.noisy_top||{}).forEach(function(k){s+='  |'+k+'>  '+(d.noisy_top[k]*100).toFixed(1)+'%\n'});s+='\nEMBEDDING sugerido (usa estos qubits): '+JSON.stringify((emb&&emb.embedding)||[])+'  evita: '+JSON.stringify((emb&&emb.avoided)||[])+'\n';s+='\nmodelo: '+d.model+'\ncaveat: '+d.caveat;p.textContent=s;}catch(e){p.textContent='error: '+e}}
async function atlasEmbedding(){var t=$('qasm'),p=$('certPanel');if(!t||!p)return;var q=t.value||'';if(!q.trim()){p.textContent='Pega un circuito OpenQASM primero.';return}p.textContent='calculando embedding óptimo (token-free, tabla de calibración medida)...';try{var e=await post('/api/embedding',{qasm:q});if(e.error){p.textContent=e.error;return}var emb=(e&&e.embedding)||[],av=(e&&e.avoided)||[];var s='ADVISOR DE EMBEDDING (token-free · sub-grafo de MENOR error CZ desde la tabla medida de ibm_kingston)\n';s+='n='+(e.n_qubits!=null?e.n_qubits:'?')+'  ·  qubits asignados: '+(e.achieved!=null?e.achieved:emb.length)+'\n\n';s+='QUBITS RECOMENDADOS (initial_layout): '+JSON.stringify(emb)+'\n';s+='QUBITS A EVITAR (readout/CZ malos): '+JSON.stringify(av)+'\n';s+='SUMA DE ERROR CZ del sub-grafo: '+(e.sum_cz_error!=null?e.sum_cz_error:'n/d')+'\n';s+='fuente: '+(e.source||'tabla pública horneada')+'\n';if(e.note)s+='nota: '+e.note+'\n';s+='\n— POR QUÉ IMPORTA (contraste MEDIDO embedding-GOOD vs TLS) —\n';s+='GHZ-6:  9.7x mejor fidelidad usando el embedding recomendado vs qubits TLS\n';s+='GHZ-4:  7.3x mejor fidelidad\n';s+='(el embedding no es cosmético: cambia el resultado en casi un orden de magnitud)';p.textContent=s;}catch(err){p.textContent='error: '+err}}
async function atlasCompute(){var t=$('qasm'),p=$('certPanel');if(!t||!p)return;var q=t.value||'';if(!q.trim()){p.textContent='Pega un circuito OpenQASM primero.';return}p.textContent='computando resultado (solo si el triage lo certifica barato)...';try{var d=await post('/api/compute',{qasm:q});if(d.error){p.textContent=d.error;return}var s;if(d.computed){s='RESULTADO COMPUTADO — '+d.method+'\n';s+='n='+d.n+(d.sampled_shots?('  ·  '+d.sampled_shots+' shots'):'')+'  ·  ruta certificada: '+(d.route||'?')+(d.exact?'  ·  EXACTO':'')+'\n\n';s+='distribución de salida ideal (top):\n';var tp=d.top||{};Object.keys(tp).forEach(function(k){var pct=(tp[k]*100).toFixed(1);var bar='█'.repeat(Math.max(0,Math.round(tp[k]*24)));s+='  |'+k+'>  '+pct+'%  '+bar+'\n'});s+='\n'+(d.note||'');}else{s='NO COMPUTADO (y eso es honesto)\n\n'+(d.reason||'')+'\n\nruta: '+(d.route||'?')+'\n\n— el caso no está certificado barato; el VEREDICTO es la respuesta, no un número inventado.';}p.textContent=s;}catch(err){p.textContent='error: '+err}}
async function atlasReachability(){var t=$('qasm'),p=$('certPanel');if(!t||!p)return;var q=t.value||'';if(!q.trim()){p.textContent='Pega un circuito OpenQASM primero.';return}p.textContent='estimando alcanzabilidad (mirror-RB, polinomial, sin statevector)...';try{var d=await post('/api/reachability',{qasm:q});if(d.error){p.textContent=d.error;return}var pf=d.predicted_fidelity||{};var s='ALCANZABILIDAD — mirror-RB (a CUALQUIER n, SIN statevector · '+(d.backend||'')+')\n';s+='n='+d.n+'  ·  capas 2q='+d.n2q_layers+'  ·  puertas 2q='+d.n2q_gates+'\n\n';s+='FIDELIDAD EFECTIVA PREDICHA (κ̂-corregida, calibración medida):\n';s+='  F_inferida (1er orden) = '+(pf.F_inferred!=null?pf.F_inferred:'?')+'\n';s+='  F_corregida (κ̂='+(d.kappa_hat!=null?d.kappa_hat:'?')+') = '+(pf.F_corrected!=null?pf.F_corrected:'?')+'   banda conformal 90%: '+JSON.stringify(pf.band)+'\n\n';s+='TECHO DE PROFUNDIDAD:\n';s+='  realista (metal, κ̂) ≈ '+d.depth_ceiling_realistic+' capas  ·  1er-orden optimista: '+JSON.stringify(d.depth_ceiling_first_order)+'\n';s+='  ALCANZABLE bajo techo realista: '+(d.reachable?'sí ✓':'no ✗')+'\n\n';var v=d.verification||{};s+='— VERIFICACIÓN EN METAL (mirror-RB) —\n';s+=v.method+'\n  lectura: '+v.readout+'\n  '+v.note+'\n';if(v.mirror_circuit_qasm){s+='\n  circuito de verificación (target='+(v.target_bitstring||'').slice(0,16)+'...): '+v.mirror_circuit_qasm.split(String.fromCharCode(10)).length+' líneas QASM — descárgalo abajo';window._mirrorQASM=v.mirror_circuit_qasm;}else if(v.unavailable){s+='\n  ('+v.unavailable+')';}s+='\n\nSCOPE: '+d.scope;p.textContent=s;if(v.mirror_circuit_qasm){var dl=document.createElement('button');dl.className='playbtn';dl.textContent='⤓ mirror.qasm';dl.onclick=function(){_dl(window._mirrorQASM,'mirror_verify.qasm')};p.appendChild(document.createElement('br'));p.appendChild(dl);}}catch(err){p.textContent='error: '+err}}
async function atlasHardware(){var p=$('certPanel');if(!p)return;p.textContent='cargando realidad del hardware (snapshot medido)...';try{var d=await post('/api/hardware',{});if(d.error){p.textContent=d.error;return}var h=d.health||{},m2=d.measure2_over_measure||{};var s='REALIDAD DEL HARDWARE — '+(d.backend||'')+' (medido '+(d.measured||'')+', snapshot estatico)\n';s+='procesador: Heron r2 · '+d.n+' qubits · '+d.edges+' couplers · treewidth(coupling)='+d.coupling_treewidth+'\n';var cf=d.calibration_freshness;if(cf&&cf.label)s+=(cf.stale?'⚠ ':'')+cf.label+'\n';s+='\n— LO QUE IBM NO SINTETIZA (todo medido) —\n';s+='CHIP EFECTIVO: el "'+d.n+'" fragmenta (CZ<0.3%) en '+JSON.stringify(h.good_components||[])+' -> componente principal de '+h.effective_main_component+' qubits\n';s+='marketing CZ: la mediana titular vs la media = '+h.cz_mean_over_median+'x (cola larga de edges rotos)\n';s+='dephasing puro: '+Math.round((h.dephasing_dominated_frac||0)*100)+'% de qubits limitados por ruido de fase (mejorar T1 no ayuda)\n';s+='dephasing severo (T2<T1/2): '+Math.round((h.dephasing_frac_T2_lt_half_T1||0)*100)+'% del chip\n';s+='gate lengths (3 generaciones de couplers): '+JSON.stringify(h.gate_lengths_ns||{})+'\n';s+='readout backaction (M2<M): '+Math.round((h.readout_backaction_M2_lt_M_frac||0)*100)+'%  ·  idle==sx: '+(h.idle_eq_sx?'si (idle estimado del gate error)':'no')+'\n';s+='measure_2/measure: mediana '+m2.median+'x, max Q'+m2.worst_q+' '+m2.max+'x ('+Math.round((m2.frac_ge_5x||0)*100)+'% >=5x)\n';s+='\n— ZONA MUERTA (dinamica + cronica) —\n';s+=(h.dead_zone_dynamic||'')+'\n'+(h.q121_chronic||'')+'\n';s+='\nqubits a excluir: '+JSON.stringify(d.exclude_qubits||[])+'\nmejores qubits: '+JSON.stringify(d.top_qubits||[])+'\n';s+='\nCAVEAT honesto: frecuencias NO en la API ('+(h.frequencies_in_api?'si':'no')+') -> loss-tangent exacto y colision espectral siguen siendo solo-IBM.\n';s+='\nNB: data estatica de calibracion publica (sin token IBM en el app). Refrescar: atlas_hardware.summarize() local.';p.textContent=s;}catch(e){p.textContent='error: '+e}}
function _fmtHarden(d){var s='TRAYECTORIA (donde cruza la frontera):\n';(d.trajectory||[]).forEach(function(r){s+='  n='+r.n+'  '+r.route+'   (mps2^'+r.mps_log2+', tw2^'+r.treewidth_log2+')\n'});var fh=d.first_hard;s+='\nprimera variante genuinamente dura: '+(fh?('n='+fh.n+'  '+fh.route):'ninguna en el rango explorado');if(fh&&fh.certificate)s+='\n  tier del certificado: '+(fh.certificate.confidence||{}).tier;return s;}
async function atlasHarden(){var t=$('qasm'),p=$('certPanel');if(!t||!p)return;var q=t.value||'';if(!q.trim()){p.textContent='Pega un circuito OpenQASM primero.';return}
  // ASYNC: arranca el job y hace poll -> no bloquea, muestra progreso
  try{var j=await post('/api/harden',{qasm:q,async:true});if(j.error){p.textContent=j.error;return}var jid=j.job_id;var tk=0;
    while(true){await new Promise(function(r){setTimeout(r,2500);});tk++;
      var st=await post('/api/harden_status',{job_id:jid});
      if(st.status==='done'){p.textContent=_fmtHarden(st);return;}
      if(st.status==='error'||st.error){p.textContent='error: '+(st.error||'desconocido');return;}
      p.textContent='explorando complejidad… ('+(tk*2.5).toFixed(0)+'s, midiendo escalas con guard por circuito)';
      if(tk>40){p.textContent='el barrido superó 100s; reintenta con menos n_max.';return;}
    }
  }catch(e){p.textContent='error: '+e}}
async function atlasSegment(){var t=$('qasm'),p=$('certPanel');if(!t||!p)return;var q=t.value||'';if(!q.trim()){p.textContent='Pega un circuito OpenQASM primero.';return}p.textContent='triage por segmento...';try{var d=await post('/api/segment',{qasm:q});if(d.error){p.textContent=d.error;return}var w=d.whole||{};var s='TRIAGE POR SEGMENTO (diagnostico: DONDE vive la dureza)\n';s+='circuito completo: '+(w.route||'')+'  best 2^'+w.union_cost_log2+' via '+(w.best_method||'')+'\n\n';(d.segments||[]).forEach(function(g,i){s+='  seg'+i+' '+(g.label||'')+'  #T='+g.t_count+'  ent='+g.n_entanglers+'  best 2^'+g.union_cost_log2+' via '+(g.best_method||'')+'\n'});s+='\nhotspot: segmento '+d.hotspot_index+' ('+(d.hotspot_label||'')+')\nNOTA: los segmentos NO suman (el entrelazamiento cruza fronteras); es un diagnostico de DONDE se localiza la dureza.';p.textContent=s;}catch(e){p.textContent='error: '+e}}
async function atlasGpu(){var t=$('qasm'),p=$('certPanel');if(!t||!p)return;var q=t.value||'';if(!q.trim()){p.textContent='Pega un circuito OpenQASM primero.';return}p.textContent='evaluando ruta GPU...';try{var d=await post('/api/gpu',{qasm:q});if(d.error){p.textContent=d.error;return}var s='RUTA GPU STATEVECTOR (advisory; frontera dinamica)\n';s+='n='+d.n+'  ruta-atlas='+d.atlas_route+'  banda='+(d.band||'')+'\n';s+='memoria statevector: '+(d.statevector_human||'?')+'  (efectiva '+(d.effective_human||'?')+')\n';s+='factible en GPU clasica: '+d.feasible_classical_gpu+(d.gpus_required!=null?('  ('+d.gpus_required+' GPUs)'):'')+'\n';s+='recomienda GPU sobre QPU: '+d.recommend_gpu_over_qpu+'\n';if(d.advice)s+='\n'+d.advice;(d.caveats||[]).forEach(function(c){s+='\n  • '+c});p.textContent=s;}catch(e){p.textContent='error: '+e}}
async function atlasBench(){var p=$('certPanel');if(!p)return;p.textContent='cargando bundle de benchmark auditable...';try{var d=await post('/api/benchmark',{});if(d.error){p.textContent=d.error;return}var m=d.metric_definition||{},e=(d.errors||{}).false_safety||{},c=d.corpus||{};var s='BENCHMARK AUDITABLE\n';s+='corpus: '+c.certified_circuits+' certificados · sha '+c.combined_sha256+'\n';s+='metrica 0.996 = '+(m.atlas_0996||'')+'\n  = '+m.correct+'/'+m.of+' = '+m.value+'\n  '+(m.note||'')+'\n';s+='falsa-seguridad: '+e.count+' (de '+e.of_hard_verified+' casos duros = '+e.rate_hard_verified+'; Wilson95 ['+(e.wilson_ci95_hard_verified||[]).join(', ')+'])\n  '+(e.ci_warning||'')+'\nfalsa-alarma: '+((d.errors||{}).false_alarm||{}).count+'\n\nbaselines de un solo estimador:\n';var b=d.single_estimator_baselines||{};Object.keys(b).forEach(function(k){s+='  '+k+': FS='+b[k].false_safety+' FA='+b[k].false_alarm+' (n='+b[k].n+')\n'});s+='\nalcance: '+((d.scope||{}).escalate_unmeasured||'')+'\nreproduce: '+d.reproduce;p.textContent=s;}catch(err){p.textContent='error: '+err}}
async function atlasVar(){var t=$('qasm'),p=$('certPanel');if(!t||!p)return;var q=t.value||'';if(!q.trim()){p.textContent='Pega un circuito OpenQASM primero.';return}p.textContent='triage variacional (coste/disparo x #evals)...';try{var d=await post('/api/variational',{qasm:q,n_params:8,n_iters:100});if(d.error){p.textContent=d.error;return}var ps=(d.per_shot&&d.per_shot.representative)||{},tot=d.total_classical_sim||{},cmp=d.comparison||{};var s='TRIAGE VARIACIONAL VQE/QAOA\n';s+='n='+d.n+'  n_params='+d.n_params+'  n_iters='+d.n_iters+'\n';s+='coste/disparo: '+(ps.verdict||'')+'\n';s+='evaluaciones: '+tot.n_evaluations_used+'  RAM pico: '+(tot.peak_ram_fits_budget?'cabe':'NO cabe')+'  tiempo~'+(tot.total_wallclock_human||'?')+'\n';s+='\nRECOMENDACION: '+(cmp.recommendation||'')+'\n'+(cmp.rationale||'');(cmp.caveats||[]).forEach(function(c){s+='\n  • '+c});p.textContent=s;}catch(e){p.textContent='error: '+e}}

function movePhaseCursor(magicCount,mpsStr,spreadStr){
  const cur=$('ph-cursor'),core=$('ph-cursor-core');if(!cur||!core)return;
  const magic=parseInt(magicCount)||0;
  const mps=parseFloat((mpsStr||'0').replace('2^',''))||0,spread=parseFloat((spreadStr||'0').replace('2^',''))||0;
  const ent=Math.min(mps+spread,12);
  const x=+(12+(ent/12)*236).toFixed(1),y=+(168-Math.min(magic/25,1)*156).toFixed(1);
  cur.setAttribute('cx',x);cur.setAttribute('cy',y);core.setAttribute('cx',x);core.setAttribute('cy',y);
  trail.push({x,y});if(trail.length>8)trail.shift();
  const g=$('ph-trail');if(g)g.innerHTML=trail.slice(0,-1).map((t,i)=>`<circle cx="${t.x}" cy="${t.y}" r="2.5" fill="#a78bfa" opacity="${(0.1+0.45*i/trail.length).toFixed(2)}"/>`).join('');}
// OUTCOME-CONSISTENT positioning: the cursor sits on the easy->nucleo diagonal at
// a fraction = real difficulty (route + heuristic score), NOT raw saturated #T.
// So a tractable circuit (heuristic ~42) lands in the TENSOR band even with #T=134;
// the nucleo (top-right) is reached ONLY when the route is genuinely ESCALATE.
function _routeFrac(r){r=(r||'').toLowerCase().replace('-','_');
  return r==='escalate'?0.93:(r==='hpc_first'||r==='hpc_review')?0.74:r==='tensor'?0.45:r==='cpu'?0.16:0.5;}
function _routeCol(r){r=(r||'').toLowerCase().replace('-','_');return r==='escalate'?'#fb7185':(r==='hpc_first'||r==='hpc_review')?'#fb923c':r==='tensor'?'#60a5fa':r==='cpu'?'#34d399':'#fde68a';}
function _phLean(magic,ent){return [Math.min(1,(parseFloat(magic)||0)/40), Math.min(1,(parseFloat(ent)||0)/14)];}
function _outcomeNorm(frac,pm,pe){
  frac=Math.max(0,Math.min(1,frac));
  var nx=0.10+frac*0.82, ny=0.12+frac*0.76;                 // diagonal easy -> real corner nucleo
  var b=Math.max(-1,Math.min(1,(pm||0)-(pe||0)));           // magic-heavy (>0) leans up-left; spread-heavy down-right
  nx+=b*0.16*(-0.71); ny+=b*0.16*(0.70);
  return {nx:Math.max(0.02,Math.min(0.98,nx)), ny:Math.max(0.03,Math.min(0.97,ny))};}
function _outcomeXY(frac,pm,pe){var n=_outcomeNorm(frac,pm,pe);return [+(12+n.nx*236).toFixed(1), +(168-n.ny*156).toFixed(1)];}
// compact mini-map for the analysis panel: 3 frontiers + where THIS circuit landed
function _miniMapSVG(o,av){
  var c=o.costs_log2||{},mps=parseFloat(c['MPS(entangle)'])||0,sp=parseFloat(c['spread(local)'])||0;
  var pm=Math.min(1,(o.t_count||0)/40),pe=Math.min(1,(mps+sp)/14),nn=_outcomeNorm((av.score||45)/100,pm,pe);
  var W=210,H=132,iw=W-16,ih=H-16,px=function(x){return (8+x*iw).toFixed(1);},py=function(y){return (H-8-y*ih).toFixed(1);};
  function el(cx,cy,rx,ry,fill,st,da){return '<ellipse cx="'+px(cx)+'" cy="'+py(cy)+'" rx="'+(rx*iw).toFixed(0)+'" ry="'+(ry*ih).toFixed(0)+'" fill="'+fill+'" stroke="'+st+'"'+(da?' stroke-dasharray="'+da+'"':'')+'/>';}
  return '<svg viewBox="0 0 '+W+' '+H+'" width="100%" preserveAspectRatio="xMidYMid meet" style="max-height:140px;background:#0a0a0e;border-radius:8px;display:block">'+
    el(0.78,0.70,0.24,0.30,'none','rgba(148,163,184,.5)','3 3')+
    el(0.84,0.80,0.17,0.22,'rgba(45,212,191,.07)','rgba(56,189,166,.6)','4 3')+
    el(0.90,0.88,0.10,0.13,'rgba(225,29,72,.2)','#fb7185',null)+
    '<circle cx="'+px(nn.nx)+'" cy="'+py(nn.ny)+'" r="6" fill="#fff" opacity="0.85"/><circle cx="'+px(nn.nx)+'" cy="'+py(nn.ny)+'" r="2.8" fill="'+_routeCol(av.route)+'"/>'+
    '<text x="7" y="'+(H-4)+'" font-family="IBM Plex Sans" font-size="7" fill="#64748b">easy</text>'+
    '<text x="'+(W-44)+'" y="13" font-family="IBM Plex Sans" font-size="7" fill="#fb7185">QPU núcleo</text></svg>';}
function _litFor(route,EN){route=(route||'').toUpperCase().replace('_','-');
  if(route==='CPU')return EN?'CPU regime: Stim simulates stabilizers in polynomial time (Gottesman-Knill); statevector is trivial at this n. Solidly inside what the field simulates routinely.':'Régimen CPU: Stim simula estabilizadores en tiempo polinomial (Gottesman-Knill); statevector es trivial a este n. Bien dentro de lo que el campo simula de rutina.';
  if(route==='TENSOR')return EN?'Tensor regime: bounded entanglement → quimb/MPS and Clifford-augmented MPS (CAMPS, 2024) simulate this class; treewidth contraction (cotengra) is an alternative. The field handles this.':'Régimen tensorial: entrelazamiento acotado → quimb/MPS y Clifford-augmented MPS (CAMPS, 2024) simulan esta clase; la contracción por treewidth (cotengra) es alternativa. El campo lo resuelve.';
  if(route==='HPC-FIRST')return EN?'HPC-review regime: the cheap-looking MPS is a TRUNCATED lower bound; contraction width governs and may exceed a single node. Tensor-network spoofing of Sycamore/IBM-utility lived near here — verify the budget before any QPU claim.':'Régimen revisión-HPC: el MPS barato es una COTA INFERIOR truncada; la anchura de contracción gobierna y puede exceder un nodo. El spoofing por tensor networks de Sycamore/utilidad-IBM vivió cerca de aquí — verifica el presupuesto antes de afirmar QPU.';
  return EN?'Real núcleo: statevector, MPS and contraction all exceed the declared budget. This is the genuine QPU/HPC frontier — not perceived hardness, measured hardness. Even here, noise on real hardware can collapse coherent hardness.':'Núcleo real: statevector, MPS y contracción exceden el presupuesto declarado. Esta es la frontera QPU/HPC genuina — no dureza percibida, dureza medida. Incluso aquí, el ruido del hardware real puede colapsar la dureza coherente.';}
function _phXY(magic,ent){var l=_phLean(magic,ent);return _outcomeXY(0.16+0.7*Math.min(1,(parseFloat(ent)||0)/12),l[0],l[1]);}
function movePhaseCursor(magicCount,mpsStr,spreadStr){
  const cur=$('ph-cursor'),core=$('ph-cursor-core');if(!cur||!core)return;
  var mps=parseFloat((mpsStr||'0').replace('2^',''))||0,spread=parseFloat((spreadStr||'0').replace('2^',''))||0;
  var l=_phLean(magicCount,mps+spread),xy=_outcomeXY(0.45,l[0],l[1]);
  cur.setAttribute('cx',xy[0]);cur.setAttribute('cy',xy[1]);core.setAttribute('cx',xy[0]);core.setAttribute('cy',xy[1]);}
function _parseQasmGates(q){(q||'');var gs=[];(q||'').split('\n').forEach(function(ln){ln=ln.trim();var m=ln.match(/^([a-z]+)/i);if(!m)return;var op=m[1].toLowerCase();
  if(['h','x','y','z','s','sdg','t','tdg','cx','cz','ccx','rx','ry','rz'].indexOf(op)>=0)gs.push(op);});return gs;}
var _phAnim=null;
// Climb gate-by-gate, but the RADIUS toward the nucleo is capped by the measured
// outcome (heuristic score / route). A tractable circuit climbs only to its band.
function animatePhaseRun(qasm,o){
  var cur=$('ph-cursor'),core=$('ph-cursor-core'),run=$('ph-run'),tg=$('ph-trail');if(!cur||!core)return;
  if(_phAnim){cancelAnimationFrame(_phAnim);_phAnim=null;}
  var av=(typeof atlasVerdict==='function'&&o)?atlasVerdict(o):{score:45,route:'TENSOR'};
  var fracMax=Math.max(0.1,Math.min(1,(av.score||45)/100)),route=av.route||'TENSOR';
  var c=(o&&o.costs_log2)||{},fE=(parseFloat(c['MPS(entangle)'])||0)+(parseFloat(c['spread(local)'])||0);
  var lean=_phLean((o&&o.t_count)||0,fE),pm=lean[0],pe=lean[1];
  var gates=_parseQasmGates(qasm),cum=0,acc=[0];
  gates.forEach(function(op){if(op==='t'||op==='tdg'||op==='ccx')cum+=1.0;if(op==='cx'||op==='cz')cum+=1.0;else if(op==='ccx')cum+=2;acc.push(cum);});
  var tot=cum||1,N=acc.length,cap=64,stride=Math.max(1,Math.floor(N/cap)),S=[];
  for(var i=0;i<N;i+=stride)S.push(acc[i]);S.push(acc[N-1]);
  var pts=S.map(function(a){return _outcomeXY(fracMax*(a/tot),pm,pe);});
  trail.length=0;if(tg)tg.innerHTML='';if(run)run.setAttribute('d','');run.setAttribute('stroke',_routeCol(route));
  var t0=null,DUR=900*Math.min(1,0.4+pts.length/64);
  function frame(ts){if(t0===null)t0=ts;var k=Math.min(1,(ts-t0)/DUR);
    var idx=Math.max(1,Math.floor(k*(pts.length-1))),p=pts[idx];
    cur.setAttribute('cx',p[0]);cur.setAttribute('cy',p[1]);core.setAttribute('cx',p[0]);core.setAttribute('cy',p[1]);
    if(run)run.setAttribute('d','M'+pts.slice(0,idx+1).map(function(q){return q[0]+' '+q[1];}).join(' L'));
    if(k<1){_phAnim=requestAnimationFrame(frame);}else{_phAnim=null;_phZonePulse(pts[pts.length-1],route);}}
  _phAnim=requestAnimationFrame(frame);
}
function _phZonePulse(xy,route){var pz=$('ph-zonepulse'),qz=$('ph-qpu');
  if(pz){pz.setAttribute('cx',xy[0]);pz.setAttribute('cy',xy[1]);pz.setAttribute('stroke',_routeCol(route));
    pz.style.animation='none';void pz.getBBox();pz.style.animation='phpulse 1.1s ease-out 2';}
  if(qz)qz.setAttribute('opacity',(route||'').toLowerCase().indexOf('escalate')>=0?'1':'0.55');}
// MIDE el avance real: cada paso se ubica por la RUTA medida de ese prefijo, asi el
// climb cruza a tensor/hpc/nucleo SOLO cuando la ruta real lo hace.
async function runMeasuredTrajectory(){var q=($('qasm')&&$('qasm').value)||'';if(!q.trim())return;
  var btn=$('phmeas');if(btn){if(!btn._t)btn._t=btn.textContent;btn.textContent=LANG==='en'?'measuring…':'midiendo…';btn.disabled=true;}
  try{var o=await post('/api/trajectory',{qasm:q,steps:14});if(o&&o.trajectory&&o.trajectory.length)animatePhaseMeasured(o.trajectory);}catch(e){}
  if(btn){btn.textContent=btn._t||'◉ Measured';btn.disabled=false;}}
function animatePhaseMeasured(pts){var cur=$('ph-cursor'),core=$('ph-cursor-core'),run=$('ph-run');if(!cur||!core||!pts.length)return;
  if(_phAnim){cancelAnimationFrame(_phAnim);_phAnim=null;}
  var P=[{xy:_outcomeXY(0.05,0,0),route:'cpu'}];
  pts.forEach(function(p){var l=_phLean(p.t_count,(parseFloat(p.mps_log2)||0)+(parseFloat(p.treewidth_log2)||0));  // fix audit: _trajectory devuelve treewidth_log2, no spread_log2 (antes NaN->0 silencioso)
    P.push({xy:_outcomeXY(_routeFrac(p.route),l[0],l[1]),route:(p.route||'cpu')});});
  var fin=pts[pts.length-1];
  trail.length=0;if(run)run.setAttribute('d','');var t0=null,DUR=1500;
  function frame(ts){if(t0===null)t0=ts;var k=Math.min(1,(ts-t0)/DUR);
    var idx=Math.max(1,Math.floor(k*(P.length-1))),p=P[idx].xy;
    cur.setAttribute('cx',p[0]);cur.setAttribute('cy',p[1]);core.setAttribute('cx',p[0]);core.setAttribute('cy',p[1]);
    if(run){run.setAttribute('stroke',_routeCol(P[idx].route));run.setAttribute('d','M'+P.slice(0,idx+1).map(function(q){return q.xy[0]+' '+q.xy[1];}).join(' L'));}
    if(k<1){_phAnim=requestAnimationFrame(frame);}else{_phAnim=null;_phZonePulse(P[P.length-1].xy,fin.route);}}
  _phAnim=requestAnimationFrame(frame);}
function _routeNice(r){return (r||'').toUpperCase().replace('_','-');}
// Panel completo al picar el mapa: percepcion vs real, ruta+confianza, contrafactuales,
// vs estimadores unicos, y donde cae esto en la literatura (encuadre honesto).
function openAnalysisPanel(o){
  o=o||window.lastAtlas;var m=document.getElementById('analysis-modal');if(!o||!m)return;
  var EN=LANG==='en',av=atlasVerdict(o),ra=o.route_adjudication||{},c=o.costs_log2||{};
  var base=ra.single_estimator_baselines||{},cf=ra.counterfactuals||[],inval=ra.invalidated_estimators||[];
  var n=o.n||0,T=o.t_count||0,mps=c['MPS(entangle)'],tw=c['contraction(treewidth)'],sp=c['spread(local)'];
  var route=av.route,score=av.score,conf=ra.confidence||{};
  var entProxy=(parseFloat(mps)||0)+(parseFloat(sp)||0);
  var perceived=(T>=12&&entProxy>=6)?(EN?'HARD (high #T + high entanglement)':'DURO (alto #T + alto entrelazamiento)'):(EN?'moderate':'moderado');
  var realCls=(route==='CPU'||route==='TENSOR')?'ok':route==='ESCALATE'?'no':'maybe';
  var crossed=(T>=12&&entProxy>=6&&(route==='CPU'||route==='TENSOR'));
  var ests=[['treewidth-only',base.treewidth_only],['mps-only',base.mps_only],['magic-only',base.magic_only]];
  var estRows=ests.map(function(p){var dis=p[1]&&_routeNice(p[1])!==_routeNice(route);
    return '<tr><td>'+p[0]+'</td><td style="text-align:right"><b style="color:'+(dis?'#fbbf24':'#94a3b8')+'">'+_routeNice(p[1]||'n/a')+'</b></td><td>'+(dis?(EN?'would diverge':'divergiría'):(EN?'agrees':'coincide'))+'</td></tr>';}).join('');
  var cfHtml=cf.length?cf.map(function(x){return '<li><b>'+x.baseline+'</b> · '+(EN?'failure mode':'modo de fallo')+': <span style="color:#fbbf24">'+x.failure_mode+'</span> — '+x.why_atlas_differs+'</li>';}).join(''):'<li style="color:#64748b">'+(EN?'no single-estimator failure modes triggered':'sin modos de fallo de estimador único')+'</li>';
  var invalHtml=inval.length?('<ul class="an-list">'+inval.map(function(e){return '<li><b>'+e.estimator+'</b> '+(e.observed||'')+' — '+e.reason+'</li>';}).join('')+'</ul>'):'';
  var html=
    '<div class="an-head"><div><div class="an-route '+realCls+'">'+_routeNice(route)+'</div><div class="an-sub">'+(EN?'measured route':'ruta medida')+' · n='+n+' · #T='+T+'</div></div>'+
      '<div class="an-score">'+score+'<span>/100</span><div class="an-conf">'+(EN?'confidence':'confianza')+' '+((conf.label||'').toUpperCase())+' '+(conf.score!=null?conf.score:'')+'</div></div></div>'+
    (/(medium|low)/i.test(conf.label||'')?'<div style="margin-bottom:12px;padding:10px 13px;border-radius:8px;border:1px solid rgba(251,191,36,.42);background:rgba(251,191,36,.10);font-size:12px;line-height:1.55;color:#fcd34d">'+'<b>⚠ '+(EN?'Reduced confidence':'Confianza reducida')+' ('+((conf.label||'').toUpperCase())+')</b> — '+(EN?'this verdict sits in the borderline calibration zone (out of distribution). The route is the honest call, but the adjudicator cannot <i>certify</i> its accuracy here. For a high-stakes decision, verify with the full-capability engine.':'este veredicto cae en la zona de calibración límite (fuera de distribución). La ruta es la llamada honesta, pero el adjudicador no puede <i>certificar</i> su accuracy aquí. Para una decisión de peso, verifícalo con el motor full-capability.')+'</div>':'')+
    '<div class="an-card" style="margin-bottom:12px"><h4>'+(EN?'Where this circuit lands':'Dónde cae este circuito')+'</h4>'+_miniMapSVG(o,av)+
      '<p style="margin-top:6px;font-size:10.5px;color:#94a3b8">'+(EN?'gray = perceived (literature) · teal = field-classical · red = real QPU núcleo · ● = your circuit':'gris = percibida (literatura) · teal = clásico del campo · rojo = núcleo QPU real · ● = tu circuito')+'</p></div>'+
    '<div class="an-grid">'+
      '<div class="an-card"><h4>'+(EN?'Perceived vs real':'Percepción vs realidad')+'</h4>'+
        '<p>'+(EN?'Literature would call this':'La literatura lo llamaría')+': <b>'+perceived+'</b></p>'+
        '<p>'+(EN?'Atlas measured route':'Ruta medida por Atlas')+': <b class="'+realCls+'">'+_routeNice(route)+'</b></p>'+
        (crossed?'<p class="an-win">'+(EN?'→ Looks hard, but a classical route exists. This sits in territory existing classical methods already handle, below the perceived frontier.':'→ Parece duro, pero existe ruta clásica. Cae en territorio que los métodos clásicos existentes ya manejan, por debajo de la frontera percibida.')+'</p>':'')+'</div>'+
      '<div class="an-card"><h4>'+(EN?'Why (governing)':'Por qué (gobernante)')+'</h4>'+
        '<p>'+(EN?'Governing estimator':'Estimador gobernante')+': <b>'+(ra.governing_estimator||'n/a')+'</b></p>'+
        '<p style="color:#94a3b8">'+(av.reason||'')+'</p>'+
        '<p style="font-family:monospace;font-size:11px;color:#7c8aa0">#T='+T+' · MPS=2^'+mps+' · TW=2^'+tw+' · spread='+(sp==null?'n/a':'2^'+sp)+'</p>'+invalHtml+'</div>'+
      '<div class="an-card"><h4>'+(EN?'vs single estimators':'vs estimadores únicos')+'</h4>'+
        '<table class="an-tbl"><thead><tr><th>'+(EN?'method':'método')+'</th><th style="text-align:right">'+(EN?'route':'ruta')+'</th><th></th></tr></thead><tbody>'+
        '<tr><td><b style="color:#38bdf8">Atlas</b></td><td style="text-align:right"><b style="color:#38bdf8">'+_routeNice(route)+'</b></td><td>'+(EN?'adjudicated':'adjudicado')+'</td></tr>'+estRows+'</tbody></table></div>'+
      '<div class="an-card"><h4>'+(EN?'Counterfactuals (which heuristic fails)':'Contrafactuales (qué heurística falla)')+'</h4><ul class="an-list">'+cfHtml+'</ul></div>'+
    '</div>'+
    '<div class="an-lit"><h4>'+(EN?'Where this sits in the literature':'Dónde cae esto en la literatura')+'</h4>'+
      '<p style="margin-bottom:6px;color:#cbd5e1">'+_litFor(route,EN)+'</p>'+
      '<p style="font-size:10.5px;color:#7c8aa0">'+(EN?'Context: the perceived↔actual gap is a field-wide result, not an Atlas discovery (Sycamore RCS & IBM-utility classically simulated; CAMPS 2024; Shallow Magic Depth PRX Quantum 2025; Qiskit Aer auto-selects). Atlas adds the operational pre-flight triage: failure-mode-aware adjudication, calibrated confidence, non-circular benchmark.':'Contexto: la brecha percibida↔real es resultado del campo, no hallazgo de Atlas (Sycamore RCS y utilidad-IBM simulados clásicamente; CAMPS 2024; Shallow Magic Depth PRX Quantum 2025; Qiskit Aer auto-selecciona). Atlas añade el triage pre-flight: adjudicación consciente de modos de fallo, confianza calibrada, benchmark no-circular.')+'</p></div>';
  document.getElementById('analysis-body').innerHTML=html;m.classList.add('open');document.body.classList.add('modal-open');  // #4 scroll-lock
  var x=m.querySelector('.an-x');if(x&&x.focus)x.focus();   // a11y: move focus into modal
}
function closeAnalysisPanel(){var m=document.getElementById('analysis-modal');if(m)m.classList.remove('open');document.body.classList.remove('modal-open');}
// ===== Fase 6: chat REAL con Claude (diagnostico del circuito como contexto) =====
var _chatMsgs=[];
function _chatDiag(){var o=window.lastAtlas;if(!o)return null;var av=(typeof atlasVerdict==='function')?atlasVerdict(o):null;
  return {n:o.n,t_count:o.t_count,verdict:o.verdict,route_adjudication:o.route_adjudication,costs_log2:o.costs_log2,
    entanglement_entropy:o.entanglement_entropy,mps_truncated:o.mps_truncated,atlas_score:(av&&av.score!=null?av.score:undefined)};}
function _cmAppend(role,content){var log=$('cm-log');if(!log)return null;var d=document.createElement('div');d.className='cm-msg '+role;d.textContent=content;log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function openChat(){var m=$('chat-modal');if(!m)return;var EN=LANG==='en';var d=_chatDiag();
  var ctx=$('cm-ctx');if(ctx)ctx.textContent=d?((EN?'context: ':'contexto: ')+'n='+d.n+' · #T='+d.t_count+' · '+((d.route_adjudication&&d.route_adjudication.route)||'n/a')):(EN?'no circuit analyzed — answers will be general':'sin circuito analizado — respuestas generales');
  if(!_chatMsgs.length){var log=$('cm-log');if(log)log.innerHTML='';
    _cmAppend('sys',d?(EN?'Ask me anything about this circuit triage diagnostic. Grounded in the measured numbers, no hype.':'Pregúntame lo que quieras sobre el triage de este circuito. Fundado en los números medidos, sin hype.'):(EN?'Analyze a circuit first for grounded answers, or ask a general question about Atlas.':'Analiza un circuito primero para respuestas concretas, o pregunta algo general sobre Atlas.'));}
  m.classList.add('open');var fab=$('chat-fab');if(fab)fab.classList.add('on');var inp=$('cm-input');if(inp)setTimeout(function(){inp.focus();},50);}
function closeChat(){var m=$('chat-modal');if(m)m.classList.remove('open');var fab=$('chat-fab');if(fab)fab.classList.remove('on');}
// V2-8: el chat es un widget flotante (burbuja) — toggle desde el FAB
function toggleChatBubble(){var m=$('chat-modal');if(m&&m.classList.contains('open'))closeChat();else openChat();}
// ===== V2-5: Modelo de Gasto como drawer enfocado (reusa los helpers de economía del panel) =====
function openGastoDrawer(){var s=parseAtlasState(),ins=s.hasResults?generateInsights(s):null,EN=LANG==='en',body=$('gasto-drawer-body');
  if(body){
    if(ins&&s.econ){
      var moneyHTML=ins.money.map(function(m){return'<div class="dp-money-row '+m.type+'"><div class="dp-money-icon">'+m.icon+'</div><div class="dp-money-text">'+m.text+'</div></div>';}).join('');
      body.innerHTML=econControlsHTML()+routeComparisonHTML(s)+econBreakdownHTML(s.econ,ins.isTractable,econTriageMaterial(s))+'<div class="dp-money">'+moneyHTML+'</div>';
      try{wireEconControls();}catch(e){}
    }else{body.innerHTML='<div class=gd-empty>'+(EN?'Analyze a circuit first to see route economics.':'Analiza un circuito primero para ver la economía de rutas.')+'</div>';}
  }
  var d=$('gasto-drawer');if(d)d.classList.add('open');document.body.classList.add('modal-open');}
function closeGastoDrawer(){var d=$('gasto-drawer');if(d)d.classList.remove('open');document.body.classList.remove('modal-open');}
// ===== V2-0: paleta de comandos (Cmd-K) — superficie única de acción =====
function _cmds(){var EN=LANG==='en';
  function safe(f){return function(){try{f();}catch(e){}};}
  function panel(){try{buildDecisionPanel();var p=$('decision-panel');if(p)p.classList.add('open');}catch(e){}}
  return [
   {g:EN?'Analyze':'Analizar', l:EN?'Analyze circuit':'Analizar circuito', k:'analizar analyze run correr', r:safe(function(){analyze();})},
   {g:EN?'Analyze':'Analizar', l:EN?'Ask Chat (Claude)':'Ask Chat (Claude)', k:'chat claude pregunta ask', r:safe(openChat)},
   {g:EN?'Analyze':'Analizar', l:EN?'Spend model':'Modelo de gasto', k:'gasto economia spend money costo drawer', r:safe(openGastoDrawer)},
   {g:EN?'Create':'Crear', l:EN?'Generate variant':'Generar variante', k:'generar variante reroll dado', r:safe(genReroll)},
   {g:EN?'Create':'Crear', l:EN?'Visual builder':'Constructor visual', k:'construir builder visual compuertas', r:safe(openBuilder)},
   {g:EN?'Create':'Crear', l:EN?'Load example':'Cargar ejemplo', k:'ejemplo example demo', r:safe(function(){setq(DEMO);})},
   {g:EN?'Create':'Crear', l:EN?'Load Clifford example':'Ejemplo Clifford', k:'clifford ejemplo estabilizador', r:safe(function(){setq(CLIFFORD_DEMO);})},
   {g:EN?'Create':'Crear', l:EN?'Hard example':'Ejemplo difícil', k:'dificil hard duro', r:safe(hardExample)},
   {g:EN?'Create':'Crear', l:EN?'Clear editor':'Limpiar editor', k:'limpiar clear vaciar', r:safe(function(){setq('');})},
   {g:'Workspace', l:'Workspace: Author', k:'author crear editar workspace', r:safe(function(){setWorkspace('author');})},
   {g:'Workspace', l:'Workspace: Triage', k:'triage veredicto verdict workspace', r:safe(function(){setWorkspace('triage');})},
   {g:'Workspace', l:'Workspace: Explore', k:'explore mapa map workspace', r:safe(function(){setWorkspace('explore');})},
   {g:EN?'Create':'Crear', l:EN?'Write QASM':'Escribir QASM', k:'qasm escribir dx', r:safe(function(){mode('dx');})},
   {g:EN?'Create':'Crear', l:EN?'Generate (dials)':'Generar (dials)', k:'generar gen dials', r:safe(function(){mode('gen');})},
   {g:EN?'Explore':'Explorar', l:EN?'Phase map: 2D':'Mapa de fases: 2D', k:'2d mapa fases explorer', r:safe(function(){phaseMode('2d');})},
   {g:EN?'Explore':'Explorar', l:EN?'Phase map: 3D':'Mapa de fases: 3D', k:'3d mapa fases research', r:safe(function(){phaseMode('3d');})},
   {g:EN?'Explore':'Explorar', l:EN?'Measured climb':'Avance medido', k:'avance medido climb trayectoria', r:safe(runMeasuredTrajectory)},
   {g:EN?'Export':'Exportar', l:EN?'Export QASM':'Exportar QASM', k:'qasm export descargar', r:safe(exportQASM)},
   {g:EN?'Export':'Exportar', l:EN?'Export QIR':'Exportar QIR', k:'qir llvm export descargar', r:safe(exportQIR)},
   {g:EN?'Export':'Exportar', l:EN?'Export report':'Exportar reporte', k:'reporte report export descargar', r:safe(exportReport)},
   {g:EN?'View':'Vista', l:EN?'Layout mode':'Modo Layout', k:'layout paneles ventanas', r:safe(function(){if(window.__atlasLM)__atlasLM.activate();})},
   {g:EN?'View':'Vista', l:EN?'Toggle language ES/EN':'Cambiar idioma ES/EN', k:'idioma language lang ingles espanol', r:safe(toggleLang)}
  ];}
var _cmdkSel=0,_cmdkList=[];
function openPalette(){var m=$('cmdk');if(!m)return;_cmdkSel=0;var inp=$('cmdk-input');if(inp)inp.value='';renderCmdk('');m.classList.add('open');document.body.classList.add('modal-open');if(inp)setTimeout(function(){inp.focus();},30);}
function closePalette(){var m=$('cmdk');if(m)m.classList.remove('open');document.body.classList.remove('modal-open');}
function renderCmdk(q){q=(q||'').toLowerCase().trim();
  _cmdkList=_cmds().filter(function(c){return !q||((c.l+' '+c.k+' '+c.g).toLowerCase().indexOf(q)>=0);});
  if(_cmdkSel>=_cmdkList.length)_cmdkSel=Math.max(0,_cmdkList.length-1);
  var box=$('cmdk-list');if(!box)return;
  box.innerHTML=_cmdkList.map(function(c,i){return '<div class="cmdk-item'+(i===_cmdkSel?' sel':'')+'" data-i="'+i+'"><span class="cmdk-g">'+c.g+'</span><span class="cmdk-l">'+c.l+'</span></div>';}).join('')||'<div class="cmdk-empty">'+(LANG==='en'?'no matches':'sin coincidencias')+'</div>';
  box.querySelectorAll('.cmdk-item').forEach(function(el){el.addEventListener('click',function(){runCmdk(+el.getAttribute('data-i'));});});}
function runCmdk(i){var c=_cmdkList[i];if(!c)return;closePalette();setTimeout(c.r,10);}
function cmdkKey(e){var inp=$('cmdk-input');
  if(e.key==='ArrowDown'){e.preventDefault();_cmdkSel=Math.min(_cmdkList.length-1,_cmdkSel+1);renderCmdk(inp?inp.value:'');}
  else if(e.key==='ArrowUp'){e.preventDefault();_cmdkSel=Math.max(0,_cmdkSel-1);renderCmdk(inp?inp.value:'');}
  else if(e.key==='Enter'){e.preventDefault();runCmdk(_cmdkSel);}}
async function chatSend(){var inp=$('cm-input'),btn=$('cm-send');if(!inp)return;var text=(inp.value||'').trim();if(!text)return;var EN=LANG==='en';
  inp.value='';_chatMsgs.push({role:'user',content:text});_cmAppend('user',text);
  if(btn)btn.disabled=true;var think=_cmAppend('bot',EN?'…thinking':'…pensando');
  try{var o=await post('/api/chat',{messages:_chatMsgs,diagnostics:_chatDiag()});
    if(think)think.remove();
    if(o&&o.reply){_chatMsgs.push({role:'assistant',content:o.reply});_cmAppend('bot',o.reply);}
    else{_cmAppend('err',(o&&o.error)||(EN?'no response':'sin respuesta'));}
  }catch(e){if(think)think.remove();_cmAppend('err',EN?'network error':'error de red');}
  if(btn)btn.disabled=false;if(inp)inp.focus();}
var lastFamilyMeta=null,phaseView='2d',cubeRot={x:-26,y:38},cubeDrag=null;
function familyMeta(m,e,core,seed){var topo='line / chain',family='Low-complexity request';
  if(core>=0.82&&m>=0.7&&e>=0.7){family='Hardness challenge request';topo='near-all-to-all dense interaction graph';}
  else if(core>=0.68&&e>=0.55){family='Dense interaction request';topo='dense interaction graph';}
  else if(core>=0.48&&e>=0.45){family='Interaction-frontier request';topo='hub-periphery interaction graph';}
  else if(e>=0.62){family='Spread-heavy request';topo=e>0.82?'heavy-hex-like':'2D grid local';}
  else if(m>=0.58){family='Magic-heavy request';topo='sparse random';}
  return {family_type:family,requested_magic:+m.toFixed(2),requested_spread:+e.toFixed(2),requested_interaction_density:+core.toFixed(2),requested_core_density:+core.toFixed(2),topology:topo,seed:seed};}
function coreDensityFor(m,e){return Math.max(0.08,Math.min(1,0.12+0.30*e+0.18*m+0.34*m*e));}  // smooth m*e interaction (no discontinuous step-bonuses)
function phaseMode(v){phaseView=v;var r=$('research3d'),b2=$('ph2db'),b3=$('ph3db');if(r)r.classList.toggle('on',v==='3d');if(b2)b2.classList.toggle('on',v==='2d');if(b3)b3.classList.toggle('on',v==='3d');document.querySelectorAll('.landscape-card').forEach(function(c){c.classList.toggle('is-3d',v==='3d');});renderPhase3D();if(v==='3d')startCubeAuto();else stopCubeAuto();}
// V2-7: auto-rotate suave del 3D (pausa al pasar el cursor)
var _cubeAuto=null,_cubeHover=false;
function startCubeAuto(){stopCubeAuto();_cubeAuto=setInterval(function(){if(!_cubeHover&&phaseView==='3d'&&document.getElementById('cube-dots'))cubeRotate(0.6,0);},90);}
function stopCubeAuto(){if(_cubeAuto){clearInterval(_cubeAuto);_cubeAuto=null;}}
function cubeRotate(dx,dy){cubeRot.y+=dx;cubeRot.x=Math.max(-72,Math.min(72,cubeRot.x+dy));renderPhase3D();}
function cubeReset(){cubeRot={x:-26,y:38};renderPhase3D();}
function cubeDragStart(e){var el=$('cube3d');if(!el)return;cubeDrag={x:e.clientX,y:e.clientY,rx:cubeRot.x,ry:cubeRot.y};el.setPointerCapture&&el.setPointerCapture(e.pointerId);e.preventDefault();}
document.addEventListener('pointermove',function(e){if(!cubeDrag)return;cubeRot.y=cubeDrag.ry+(e.clientX-cubeDrag.x)*0.55;cubeRot.x=Math.max(-72,Math.min(72,cubeDrag.rx-(e.clientY-cubeDrag.y)*0.45));renderPhase3D();});
document.addEventListener('pointerup',function(){cubeDrag=null;});
// Reaching genuine hardness REQUIRES scale: clicking toward the nucleo generates a
// larger circuit, so the heuristic actually moves (a small n is always tractable).
function _phNFor(core){return Math.max(6,Math.min(32,Math.round(8+core*26)));}
function clickPhase(e){let r=$('phase').getBoundingClientRect();let x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;
  // posicion CONTINUA -> densidades continuas (no high/low): el clic en el diagrama mueve magia/spread de verdad
  let mag=Math.max(0,Math.min(1,1-y)),ent=Math.max(0,Math.min(1,x));
  var core=coreDensityFor(mag,ent);var gn=$('gn');if(gn)gn.value=_phNFor(core);
  var pr=genFamily(+mag.toFixed(2),+ent.toFixed(2),core);
  if(pr&&pr.then)pr.then(function(){openAnalysisPanel(window.lastAtlas);});}
// 20 ejemplos SEMBRADOS en el mapa de densidades (5 por cuadrante). Cada punto -> genAt(magia,entangle).
var PH_PRESETS=[
  {m:0.15,e:0.15,c:0.12},{m:0.30,e:0.25,c:0.18},{m:0.20,e:0.40,c:0.25},{m:0.42,e:0.18,c:0.22},{m:0.36,e:0.38,c:0.30},
  {m:0.62,e:0.15,c:0.28},{m:0.78,e:0.28,c:0.38},{m:0.90,e:0.20,c:0.42},{m:0.66,e:0.40,c:0.46},{m:0.88,e:0.42,c:0.55},
  {m:0.15,e:0.62,c:0.42},{m:0.30,e:0.78,c:0.55},{m:0.20,e:0.90,c:0.62},{m:0.42,e:0.66,c:0.58},{m:0.38,e:0.88,c:0.70},
  {m:0.62,e:0.62,c:0.68},{m:0.78,e:0.76,c:0.82},{m:0.90,e:0.86,c:0.96},{m:0.66,e:0.90,c:0.86},{m:0.88,e:0.62,c:0.78}
];
function _phColor(m,e,c){return c>0.8?'#f87171':c>0.6?'#fbbf24':(m>0.5?'#a78bfa':(e>0.5?'#60a5fa':'#2dd4bf'));}
function renderPhaseDots(){var g=document.getElementById('ph-dots');if(!g)return;
  g.innerHTML=PH_PRESETS.map(function(p){var cx=(12+p.e*236).toFixed(1),cy=(168-p.m*156).toFixed(1),col=_phColor(p.m,p.e,p.c);
    return '<circle class=ph-dot cx="'+cx+'" cy="'+cy+'" r="'+(2.4+3.2*p.c).toFixed(1)+'" fill="'+col+'" stroke="#0a0a0e" stroke-width="1" onclick="genPreset(event,'+p.m+','+p.e+','+p.c+')"><title>'+familyMeta(p.m,p.e,p.c,genSeed).family_type+' · magic '+Math.round(p.m*100)+'% · spread '+Math.round(p.e*100)+'% · interaction density '+Math.round(p.c*100)+'%</title></circle>';
  }).join('');renderFrontiers();renderPhase3D();}
// Position the 3 frontier rings from DATA (build_frontier.py): each ring passes
// through the empirical route-boundary frac on the easy->núcleo diagonal; smaller
// frac (closer to easy) => larger ring. Badge shows the measured reclaimed %.
function renderFrontiers(){var F=window.ATLAS_FRONTIER||{};if(F.field_frac==null)return;
  var C=_outcomeXY(1,0,0);
  function ring(id,frac,minr){var el=document.getElementById(id);if(!el||frac==null)return;
    var P=_outcomeXY(frac,0,0),r=Math.max(minr||0,Math.hypot(C[0]-P[0],C[1]-P[1]));
    el.setAttribute('cx',C[0]);el.setAttribute('cy',C[1]);el.setAttribute('rx',r.toFixed(1));el.setAttribute('ry',(r*0.9).toFixed(1));}
  ring('ph-core',F.perceived_frac,40);ring('ph-field',F.field_frac,28);ring('ph-atlas-core',F.nucleo_frac,22);
  var b=document.getElementById('ph-reclaimed');if(b&&F.reclaimed_pct!=null)b.textContent=(LANG==='en'?'identified as classically reachable: ':'identificado como alcanzable clásicamente: ')+F.reclaimed_pct+'%';}
function cubeProject(x,y,z){var ax=cubeRot.x*Math.PI/180,ay=cubeRot.y*Math.PI/180;
  var X=(x-.5)*1.85,Y=(y-.5)*1.85,Z=(z-.5)*1.85;
  var cy=Math.cos(ay),sy=Math.sin(ay),cx=Math.cos(ax),sx=Math.sin(ax);
  var x1=X*cy+Z*sy,z1=-X*sy+Z*cy,y1=Y*cx-z1*sx,z2=Y*sx+z1*cx;
  var persp=1/(1+z2*0.33),scale=66*persp;
  return {x:132+x1*scale,y:106-y1*scale,z:z2,p:persp};
}
function cubeSeg(a,b,cls){var dx=b.x-a.x,dy=b.y-a.y,len=Math.sqrt(dx*dx+dy*dy),ang=Math.atan2(dy,dx)*180/Math.PI;
  return '<div class="'+cls+'" style="left:'+a.x.toFixed(1)+'px;top:'+a.y.toFixed(1)+'px;width:'+len.toFixed(1)+'px;transform:rotate('+ang.toFixed(1)+'deg);opacity:'+Math.max(.22,Math.min(.85,(a.p+b.p)/2)).toFixed(2)+'"></div>';}
function renderPhase3D(){var g=$('cube-dots');if(!g)return;
  var corners=[];for(var x=0;x<=1;x++)for(var y=0;y<=1;y++)for(var z=0;z<=1;z++)corners.push(cubeProject(x,y,z));
  var edgePairs=[[0,4],[1,5],[2,6],[3,7],[0,2],[1,3],[4,6],[5,7],[0,1],[2,3],[4,5],[6,7]];
  var html=edgePairs.map(function(e){return cubeSeg(corners[e[0]],corners[e[1]],'cube-edge');}).join('');
  for(var t=.25;t<1;t+=.25){html+=cubeSeg(cubeProject(0,t,0),cubeProject(1,t,0),'cube-gridline');html+=cubeSeg(cubeProject(t,0,0),cubeProject(t,1,0),'cube-gridline');html+=cubeSeg(cubeProject(0,0,t),cubeProject(1,0,t),'cube-gridline');}
  var pts=PH_PRESETS.map(function(p){var q=cubeProject(p.e,p.m,p.c);q.preset=p;return q;}).sort(function(a,b){return a.z-b.z;});
  html+=pts.map(function(q){var p=q.preset,col=_phColor(p.m,p.e,p.c),meta=familyMeta(p.m,p.e,p.c,genSeed),sz=(6+5*p.c)*q.p;
    return '<div class=cube-dot onclick="genPreset(event,'+p.m+','+p.e+','+p.c+')" style="left:'+q.x.toFixed(1)+'px;top:'+q.y.toFixed(1)+'px;width:'+sz.toFixed(1)+'px;height:'+sz.toFixed(1)+'px;background:'+col+';opacity:'+Math.max(.52,Math.min(1,q.p)).toFixed(2)+'"><title>'+meta.family_type+' · magic '+Math.round(p.m*100)+'% · spread '+Math.round(p.e*100)+'% · interaction density '+Math.round(p.c*100)+'%</title></div>'+(p.c>0.78?'<div class=cube-label style="left:'+(q.x+7).toFixed(1)+'px;top:'+(q.y-5).toFixed(1)+'px">'+meta.topology+'</div>':'');}).join('');
  g.innerHTML=html;var ro=$('cube-readout');if(ro)ro.textContent='rot X '+Math.round(cubeRot.x)+'° · Y '+Math.round(cubeRot.y)+'° · click point = generate family';}
function genFamily(m,en,core){var meta=familyMeta(m,en,core,genSeed),book=core<0.22?'free':'core';lastFamilyMeta=meta;dials.Tw=core>0.72?'high':'low';return genAt(+m.toFixed(2),+en.toFixed(2),book,meta);}
function genPreset(e,m,en,core){if(e&&e.stopPropagation)e.stopPropagation();var cd=core==null?coreDensityFor(m,en):+core;var gn=$('gn');if(gn)gn.value=_phNFor(cd);var pr=genFamily(+m.toFixed(2),+en.toFixed(2),cd);if(pr&&pr.then)pr.then(function(){openAnalysisPanel(window.lastAtlas);});}

// MODELO DE RUIDO (espejo de noise.py): el veredicto coherente -> rango [ruidoso, coherente].
function noiseModel(hard,magic,n2q,p,budget,n){budget=budget||40;
  var lam=p*n2q,phi=lam>1e-12?Math.min(1,1/lam):1,nh=hard*phi;
  var F=(n!=null)?(1/Math.pow(2,n)+(1-1/Math.pow(2,n))*Math.pow(1-p,n2q)):Math.exp(-lam);  // forma cerrada exacta
  var reg=lam<0.3?'coherente':lam>3?'ruido domina':'transicion';
  var pcrit=(hard>budget&&n2q>0)?(hard/budget)/n2q:null;
  return {lam:lam,F:F,phi:phi,nh:nh,reg:reg,ntract:nh<=budget,pcrit:pcrit};}
function structureLabel(x){return x==='core'?'interacting':(x||'n/a');}
function renderNoise(){var o=window.lastAtlas,out=$('noise-out');if(!o||o.hardness_log2==null||!out)return;
  var EN=LANG==='en',p=(+($('noise-p').value||5))/1000;
  var pl=$('noise-pl');if(pl)pl.textContent=(p*100).toFixed(p<0.01?2:1)+'%';
  if(!(o.n_2q>0)){out.innerHTML=EN?'No 2-qubit gates: noise has no entangling channel to act on.':'Sin compuertas de 2 qubits: el ruido no tiene canal entrelazante sobre el que actuar.';return;}
  var m=noiseModel(o.hardness_log2,o.t_count||0,o.n_2q,p,40,o.n);
  var reg=EN?({coherente:'coherent',transicion:'transition','ruido domina':'noise dominates'}[m.reg]):m.reg;
  var h='<div style="margin:0 0 6px;padding:4px 8px;background:rgba(248,113,113,0.12);border:1px solid rgba(248,113,113,0.35);border-radius:5px;color:#fca5a5;font-weight:600;font-size:11px">'+(EN?'⚠ TOY GLOBAL envelope (heuristic depolarizing shortcut) — NOT a validated local 2-qubit physical model. Use for intuition, not for a fidelity claim. Local-channel validation is declared pending in WHAT NEXT.':'⚠ Envolvente GLOBAL de juguete (atajo depolarizante heurístico) — NO es un modelo físico local 2-qubit validado. Sirve para intuición, no para una afirmación de fidelidad. La validación de canal local está declarada pendiente en WHAT NEXT.')+'</div>';
  h+=(EN?'λ = p·G = ':'λ = p·G = ')+m.lam.toFixed(2)+(EN?' expected errors · fidelity F ~ ':' errores esperados · fidelidad F ~ ')+m.F.toFixed(3)+(EN?' (global envelope)':' (envolvente global)')+'<br>';
  // Gap#4: F del MODELO LOCAL anclado en el CZ MEDIDO de ibm_kingston (no el slider toy-global).
  var CZ_MED=2.03e-3,RO_MED=7.93e-3;  // medianas medidas live (snapshot 2026-06-22, ver IBM_KINGSTON.md)
  var Floc=Math.pow(1-CZ_MED,o.n_2q)*Math.pow(1-RO_MED,o.n||0);
  h+='<span style="color:#34d399">'+(EN?'F (LOCAL model, measured ibm_kingston CZ='+CZ_MED.toExponential(2)+', readout='+RO_MED.toExponential(2)+'): ~':'F (modelo LOCAL, CZ medido ibm_kingston='+CZ_MED.toExponential(2)+', readout='+RO_MED.toExponential(2)+'): ~')+Floc.toFixed(3)+'</span> '+(EN?'[per-gate measured, not toy-global; full per-edge NoiseModel validated in noise_local_validation.csv]':'[por-gate medido, no toy-global; NoiseModel per-edge completo validado en noise_local_validation.csv]')+'<br>';
  h+=(EN?'Coherent: 2^':'Coherente: 2^')+o.hardness_log2+' &rarr; '+(EN?'noisy: 2^':'con ruido: 2^')+m.nh.toFixed(1)+' <span style="color:#94a3b8">('+reg+')</span><br>';
  h+='<b style="color:'+(m.ntract?'#34d399':'#f87171')+'">'+(m.ntract?(EN?'✓ classically TRACTABLE under this noise':'✓ clásicamente TRATABLE bajo este ruido'):(EN?'✗ still hard under this noise':'✗ sigue dura bajo este ruido'))+'</b>';
  if(m.pcrit!=null)h+='<div style="margin-top:6px;padding:4px 8px;background:rgba(251,191,36,0.12);border-radius:5px;color:#fbbf24;font-weight:600">'+(EN?'⚡ noise death-line: classically tractable from p* ≈ ':'⚡ línea de muerte por ruido: clásicamente tratable desde p* ≈ ')+(m.pcrit*100).toFixed(2)+'%'+(EN?' (below any real hardware)':' (por debajo de cualquier hardware real)')+'</div>';
  out.innerHTML=h;
  // HORIZONTE DE RUIDO en el diagrama de fases: la esquina intratable que el ruido a tasa p reclama.
  var nb=document.getElementById('ph-noise'),nl=document.getElementById('ph-noise-lbl');
  if(nb){var op=Math.min(0.45,m.lam/6);nb.setAttribute('opacity',op.toFixed(3));
    if(nl)nl.setAttribute('opacity',(op>0.05?0.8:0).toFixed(2));}}
function metrics(o){let c=o.costs_log2,gt=o.gt_ok?' &#10003;':'';let best=o.best_method||'';
  var box=$('metrics');if(!box)return;
  let pw=function(v){return v==null?'n/a':'2^'+v;};
  // #1 (inferencia Kingston): treewidth GREEDY es cota superior FLOJA. Si no es exacto y el
  // MPS lo contradice (mucho menor), marcarlo para que no se lea como dureza. El gobernante manda.
  var _tw=c['contraction(treewidth)'],_mps=c['MPS(entangle)'];
  var _twLoose=(o.treewidth_exact===false)&&_tw!=null&&_mps!=null&&(_tw-_mps>=4);
  var _twTag=_twLoose?(LANG==='en'?' · greedy upper bound (loose; does NOT govern — MPS does)':' · cota greedy (floja; NO gobierna — manda MPS)'):(o.treewidth_exact?(LANG==='en'?' · exact':' · exacto'):'');
  let cells=[['magia(#T)','var(--vio)',o.t_count,'fold(magic)'],['estructura','var(--teal)',structureLabel(o.libro_flattener),''],
    ['MPS bond','#60a5fa',(o.ground_truth&&o.ground_truth.validations&&o.ground_truth.validations.mps_truncated?'>= ':'')+pw(c['MPS(entangle)'])+(gt?' ✓':''),'MPS(entangle)'],
    ['spread','var(--green)',pw(c['spread(local)']),'spread(local)'],
    [(LANG==='en'?'treewidth w (cost 2^w)':'treewidth w (coste 2^w)'),'var(--ts)',(c['contraction(treewidth)']==null?'n/a':'w='+c['contraction(treewidth)']+' → '+pw(c['contraction(treewidth)']))+(gt?' ✓':'')+_twTag,'contraction(treewidth)']];
  box.innerHTML=cells.map(m=>{var tip='';if(m[2]==='n/a'){var msg=m[3]==='spread(local)'?(LANG==='en'?'not computed: Pauli propagation only for n<=14 (NOT a Clifford n/a)':'no computado: propagacion de Pauli solo para n<=14 (NO es n/a de Clifford)'):(LANG==='en'?'not computed: fast path n>18 (needs the exponential arsenal)':'no computado: fast path n>18 (requiere el arsenal exponencial)');tip=' title="'+msg+'"';}return `<div class="mcard${best==m[3]?' hl':''}"${tip}><span class=l><span class=d style=background:${m[1]}></span>${m[0]}</span><span class=val>${m[2]}</span></div>`;}).join('')}
function renderHistory(){var el=$('history');if(!el)return;var EN=LANG==='en',xs=[];try{xs=JSON.parse(localStorage.getItem('atlas-history')||'[]')}catch(e){}
  if(!xs.length){el.innerHTML='<div class=hist-empty>'+(EN?'Recent diagnostics will appear here.':'Los ultimos diagnosticos apareceran aqui.')+'</div>';return;}
  el.innerHTML=xs.map(function(h,i){return '<div class=hist-item onclick="loadHistory('+i+')"><div class=hist-top><span>'+h.score+'/100 · '+h.band+'</span><span>'+h.method+'</span></div><div class=hist-sub>'+h.hash+' · #T '+h.t+' · '+h.verdict+'</div></div>';}).join('');}
function saveHistory(o,av){var q=o.qasm_in||(($('qasm')&&$('qasm').value)||''),xs=[];try{xs=JSON.parse(localStorage.getItem('atlas-history')||'[]')}catch(e){}
  var h={qasm:q,hash:_hash32(q),score:av.score,band:av.band,method:o.best_method||'n/a',t:o.t_count||0,verdict:o.verdict||'',ts:Date.now()};
  xs=[h].concat(xs.filter(function(x){return x.hash!==h.hash;})).slice(0,8);try{localStorage.setItem('atlas-history',JSON.stringify(xs));}catch(e){}renderHistory();}
function loadHistory(i){try{var xs=JSON.parse(localStorage.getItem('atlas-history')||'[]');if(xs[i]&&xs[i].qasm)setq(xs[i].qasm);}catch(e){}}
function scoreTreeHTML(av){var EN=LANG==='en',p=av.parts||{};return '<div class=score-tree><div class=root>'+av.score+'/100 '+(EN?'heuristic diagnostic index':'indice diagnostico heuristico')+'</div>'+
  '<div class=leaf><span>base / verdict prior</span><b>'+p.base+'</b></div>'+
  '<div class=leaf><span>#T / magic</span><b>'+p.magic+'</b></div>'+
  '<div class=leaf><span>treewidth</span><b>'+p.treewidth+'</b></div>'+
  '<div class=leaf><span>MPS bond</span><b>'+p.mps+'</b></div>'+
  '<div class=leaf><span>Pauli spread</span><b>'+p.spread+'</b></div>'+
  '<div class=leaf><span>'+(EN?'triage clamp':'ajuste de triage')+'</span><b>'+p.clamp+'</b></div><div style="margin-top:6px;color:#64748b">'+(EN?'Weights are heuristic until benchmark calibration is complete.':'Los pesos son heuristicos hasta completar calibracion por benchmark.')+'</div></div>';}
function atlasConfidence(o,prov){var gt=o.ground_truth||{},vals=gt.validations||{},methods=gt.methods||{},keys=Object.keys(methods);
  var coverage=keys.length?keys.filter(function(k){return !!methods[k];}).length/keys.length:0.25,agreement=1;
  Object.keys(vals).forEach(function(k){var v=vals[k];if(typeof v==='string'&&/DIVERGENCIA|INCONSISTENTE|SUB|SOBRE/.test(v))agreement-=0.18;if(k==='mps_truncated'&&v)agreement-=0.22;});
  if(prov)agreement-=0.12;
  var c=o.costs_log2||{},spreadKnown=c['spread(local)']!=null,exactness=0.35+(spreadKnown?0.25:0)+(vals.treewidth_exact?0.2:0)+(!vals.mps_truncated?0.2:0);
  var n=+(o.n||0),scale=n<=14?1:n<=20?0.85:0.65,score=Math.max(0,Math.min(100,Math.round(100*coverage*Math.max(0,agreement)*Math.min(1,exactness)*scale)));
  var label=score>=75?(LANG==='en'?'High':'Alta'):score>=45?(LANG==='en'?'Medium':'Media'):(LANG==='en'?'Low':'Baja');
  return {score:score,label:label,detail:'cov '+coverage.toFixed(2)+' · agree '+Math.max(0,agreement).toFixed(2)+' · exact '+Math.min(1,exactness).toFixed(2)+' · scale '+scale.toFixed(2)};}
function _bytesHuman(x){if(!isFinite(x)||x<=0)return 'n/a';var u=['B','KB','MB','GB','TB','PB','EB'],i=0;while(x>=1024&&i<u.length-1){x/=1024;i++;}return (x>=10?x.toFixed(0):x.toFixed(1))+' '+u[i];}
function atlasVerdict(o){var EN=LANG==='en',c=o.costs_log2||{},v=o.verdict||'',best=o.best_method||'',tw=+(c['contraction(treewidth)']||0),mps=+(c['MPS(entangle)']||0),sp=c['spread(local)'],T=+(o.t_count||0);
  var intract=/INTRACTABLE|WALL|nucleo/i.test(v),prov=/PROVISIONAL|TRUNCAD|lower bound|cota inferior/i.test(v),tract=/TRACTABLE/i.test(v)&&!intract&&!prov;
  var ra=o.route_adjudication||null;
  var base=intract?72:prov?54:14,pm=Math.min(18,T/2),ptw=Math.min(16,tw/3),pmps=Math.min(12,mps*1.5),psp=sp==null?4:Math.min(12,sp*3);
  var raw=Math.max(0,Math.min(100,Math.round(base+pm+ptw+pmps+psp))),score=raw;
  // #39: position within each band CONTINUOUSLY by the governing hardness (max of
  // treewidth / MPS bond) so distinct large circuits get distinct scores instead
  // of all clamping to the same band edge.
  var hard=Math.max(tw,mps);
  if(tract)score=Math.min(score,42);
  else if(intract)score=Math.max(72,Math.min(100,Math.round(72+(hard-40)*0.7)));
  else if(prov)score=Math.max(45,Math.min(70,Math.round(45+(hard-20)*0.9)));
  var parts={base:Math.round(base),magic:Math.round(pm),treewidth:Math.round(ptw),mps:Math.round(pmps),spread:Math.round(psp),clamp:(score-raw>0?'+':'')+(score-raw)};
  var route=ra&&ra.route?ra.route:(tract?(best==='fold(magic)'||(sp!=null&&sp<=1)?'CPU':'TENSOR'):intract?'ESCALATE':'HPC_FIRST');
  if(route==='HPC_FIRST')route='HPC-FIRST';
  tract=(route==='CPU'||route==='TENSOR');intract=(route==='ESCALATE');prov=(route==='HPC-FIRST');
  var answer=route;
  var cls=(route==='CPU'||route==='TENSOR')?'yes':route==='ESCALATE'?'no':'maybe';
  var title=route==='CPU'?(EN?'Use a lightweight classical route.':'Usar una ruta clasica ligera.'):
    route==='TENSOR'?(EN?'Use tensor-network simulation; QPU is not justified.':'Usar simulacion tensorial; QPU no esta justificado.'):
    route==='HPC-FIRST'?(EN?'Run an HPC/tensor review before any QPU decision.':'Ejecutar revision HPC/tensor antes de decidir QPU.'):
    (EN?'Escalate only after classical routes fail declared budgets.':'Escalar solo si las rutas clasicas fallan los presupuestos declarados.');
  var reason=ra&&ra.governing_reason?ra.governing_reason:'';if(!reason){if(/spread/i.test(best||v))reason=EN?'Local Pauli spread remains bounded.':'La propagacion local de Pauli permanece acotada.';else if(/treewidth|contraction/i.test(best||v))reason=EN?'Tensor contraction width dominates the cost.':'La anchura de contraccion tensorial domina el coste.';else if(/MPS|entangle/i.test(best||v))reason=EN?'MPS bond dimension is the limiting estimator.':'La dimension de enlace MPS es el estimador limitante.';else reason=T>0?(EN?'Non-Clifford magic raises simulation cost.':'La magia no-Clifford eleva el coste de simulacion.'):(EN?'The circuit stays close to a Clifford/product regime.':'El circuito permanece cerca de un regimen Clifford/producto.');}
  var mem=tract?(_bytesHuman(16*Math.pow(2,Math.max(0,sp==null?mps:sp)))):(_bytesHuman(16*Math.pow(2,Math.min(tw,50)))+(tw>50?' +':''));
  var cf=atlasConfidence(o,prov),conf=cf.label+' ('+cf.score+'/100 · '+cf.detail+')';
  if(ra&&ra.confidence)conf=(ra.confidence.label||'').toUpperCase()+' ('+ra.confidence.score+'/100 · route adjudicator)';
  var band=score<30?(EN?'Easy route':'Ruta facil'):score<60?(EN?'Moderate route':'Ruta moderada'):score<80?(EN?'HPC review':'Revision HPC'):(EN?'Escalation review':'Revision de escalamiento');
  // A1: declare WHICH simulation task the verdict certifies (the governing estimator decides).
  // Pauli spread only bounds LOCAL observable expectations; it does NOT certify full sampling.
  var gov=(ra&&ra.governing_estimator?String(ra.governing_estimator):(best||'')).toLowerCase();
  var target;
  if(route==='HPC-FIRST'||route==='ESCALATE')target=EN?'none — candidate defer: no classical route certified under the declared budget':'ninguno — defer candidato: ninguna ruta clasica certificada bajo el presupuesto declarado';
  else if(/spread|fold/.test(gov)||(T>0&&sp!=null&&sp<=2&&!/statevector|mps|treewidth|stim/.test(gov)))target=EN?'LOCAL Pauli-observable expectation values — NOT full-distribution sampling or arbitrary amplitudes':'valores esperados de observables LOCALES de Pauli — NO muestreo de la distribucion completa ni amplitudes arbitrarias';
  else if(/stim|clifford/.test(gov)||T===0)target=EN?'full stabilizer simulation (sampling + Pauli expectations), exact for Clifford':'simulacion estabilizadora completa (muestreo + valores Pauli), exacta para Clifford';
  else if(/statevector/.test(gov))target=EN?'full statevector — all amplitudes and full-distribution sampling':'statevector completo — todas las amplitudes y muestreo de la distribucion completa';
  else if(/mps|entangle/.test(gov))target=EN?'full-state simulation via MPS — all amplitudes, within bond-dimension truncation':'simulacion de estado completo via MPS — todas las amplitudes, dentro de la truncacion de bond';
  else if(/treewidth|contraction/.test(gov))target=EN?'full tensor-network contraction (amplitudes / sampling) at cost ~2^treewidth':'contraccion tensorial completa (amplitudes / muestreo) a coste ~2^treewidth';
  else target=EN?'classical simulation under the measured proxies':'simulacion clasica bajo los proxies medidos';
  return {question:EN?'Recommended compute route under measured diagnostics?':'¿Ruta de computo recomendada bajo diagnosticos medidos?',answer:answer,route:route,cls:cls,title:title,reason:reason,memory:mem,confidence:conf,score:score,band:band,tract:tract,intract:intract,prov:prov,parts:parts,certifiedTarget:target};
}
function atlasRecommendation(o,av){var EN=LANG==='en',c=o.costs_log2||{},sp=c['spread(local)'],mps=+(c['MPS(entangle)']||0),tw=+(c['contraction(treewidth)']||0);
  if(av.tract&&sp!=null&&sp<=1)return {title:EN?'Run on laptop.':'Ejecutar en laptop.',items:EN?['✓ Stim / Pauli propagation is sufficient','✗ Do not spend QPU time','✗ Tensor contraction unnecessary','Estimated runtime: <1 second']:['✓ Stim / propagacion de Pauli es suficiente','✗ No gastar tiempo QPU','✗ Contraccion tensorial innecesaria','Tiempo estimado: <1 segundo']};
  if(av.tract&&mps<=10)return {title:EN?'Use tensor-network simulation.':'Usar simulacion tensorial.',items:EN?['✓ quimb / MPS recommended','✗ QPU not justified','✓ The hardness halo was flattened by measured structure','Estimated runtime: seconds to minutes']:['✓ quimb / MPS recomendado','✗ QPU no justificado','✓ El halo de dureza fue aplanado por la estructura medida','Tiempo estimado: segundos a minutos']};
  if(av.intract)return {title:EN?'Evaluate HPC first; QPU only after validation.':'Evaluar HPC primero; QPU solo tras validar.',items:EN?['✗ Statevector simulation is not practical','✓ Run cotengra / tensor-network budget review','✓ Treat QPU as candidate only if classical routes fail','Estimate noise before claiming advantage']:['✗ Statevector no es practico','✓ Revisar presupuesto con cotengra / tensor networks','✓ Tratar QPU como candidato solo si fallan rutas clasicas','Estimar ruido antes de afirmar ventaja']};
  return {title:EN?'Run an HPC pre-check.':'Hacer pre-check HPC.',items:EN?['✓ Try cotengra path search','✓ Compare MPS vs treewidth','✗ QPU decision is premature','Resolve lower-bound warning first']:['✓ Probar path search con cotengra','✓ Comparar MPS vs treewidth','✗ Decision QPU prematura','Resolver primero la cota inferior']};
}
function explainWhy(o,av){var EN=LANG==='en',c=o.costs_log2||{},sp=c['spread(local)'],mps=c['MPS(entangle)'],tw=c['contraction(treewidth)'],T=o.t_count||0,b=o.best_method||'';
  if(/spread/i.test(b)||(/spread/i.test(o.verdict||'')))return {label:EN?'Why this circuit is easy':'Por que este circuito es facil',main:EN?'Pauli propagation remains local.':'La propagacion de Pauli permanece local.',observed:sp==null?'n/a':'2^'+sp,threshold:'2^6',detail:EN?'No exponential operator growth detected; local structure bounds the simulation path.':'No se detecta crecimiento exponencial del operador; la estructura local acota la simulacion.',k1:'spread',v1:sp==null?'n/a':'2^'+sp,k2:'MPS',v2:'2^'+mps,k3:'treewidth',v3:'2^'+tw};
  var _trunc=/PROVISIONAL|TRUNCAD|cota inferior|lower bound/i.test(o.verdict||'')||o.mps_truncated;
  if(/MPS|entangle/i.test(b)&&(_trunc||!av.tract))return {label:EN?'Why this needs HPC review (not tensor networks)':'Por que requiere revision HPC (no redes tensoriales)',main:EN?'MPS is a TRUNCATED lower bound — tensor networks do NOT certify a cheap route here.':'El MPS es una COTA INFERIOR truncada — las redes tensoriales NO certifican una ruta barata aqui.',observed:'>=2^'+mps,threshold:'2^'+tw+' (treewidth)',detail:EN?'The reported MPS bond is a floor; contraction width 2^'+tw+' governs and may exceed the budget.':'El bond MPS reportado es un piso; la anchura de contraccion 2^'+tw+' gobierna y puede exceder el presupuesto.',k1:'MPS (trunc)',v1:'>=2^'+mps,k2:'treewidth',v2:'2^'+tw,k3:'#T',v3:T};
  if(/MPS|entangle/i.test(b))return {label:EN?'Why tensor networks work':'Por que funcionan redes tensoriales',main:EN?'Entanglement growth is bounded.':'El crecimiento de entrelazamiento esta acotado.',observed:'2^'+mps,threshold:'2^10',detail:EN?'The MPS bond dimension stays within a practical classical range.':'La dimension de enlace MPS permanece en un rango clasico practico.',k1:'MPS',v1:'2^'+mps,k2:'#T',v2:T,k3:'treewidth',v3:'2^'+tw};
  if(av.intract)return {label:EN?'Why this circuit is hard':'Por que este circuito es duro',main:EN?'Tensor contraction width dominates the cost.':'La anchura de contraccion domina el coste.',observed:'2^'+tw,threshold:'2^40',detail:EN?'Exact simulation grows beyond ordinary classical budgets; QPU/HPC evaluation becomes defensible.':'La simulacion exacta supera presupuestos clasicos ordinarios; QPU/HPC se vuelve defendible.',k1:'treewidth',v1:'2^'+tw,k2:'#T',v2:T,k3:'MPS',v3:'2^'+mps};
  return {label:EN?'Why the verdict is mixed':'Por que el veredicto es mixto',main:EN?'The metrics disagree enough to require a budget check.':'Las metricas discrepan y requieren contraste de presupuesto.',observed:'2^'+tw,threshold:'budget-specific',detail:EN?'Treat the current score as a triage result, not a final hardware decision.':'Trata el score como triaje, no como decision final de hardware.',k1:'treewidth',v1:'2^'+tw,k2:'MPS',v2:'2^'+mps,k3:'#T',v3:T};
}
function methodHTML(){var EN=LANG==='en',steps=EN?[
  ['Circuit','Parse OpenQASM and normalize the supported gate set.'],['Magic estimator','Count and independently inspect non-Clifford structure.'],['Pauli spread','Track local operator growth when n is small enough.'],['Tensor metrics','Estimate MPS bond and contraction treewidth.'],['Multi-method consistency','Check which estimators ran and whether their diagnostic signals agree.'],['Operational triage','Recommend CPU / tensor-network / HPC-first / QPU-later path under measured proxies.']]:[
  ['Circuito','Parsea OpenQASM y normaliza el conjunto de compuertas soportado.'],['Estimador de magia','Cuenta e inspecciona estructura no-Clifford de forma independiente.'],['Pauli spread','Rastrea crecimiento local del operador cuando n lo permite.'],['Metricas tensoriales','Estima enlace MPS y treewidth de contraccion.'],['Consistencia multi-metodo','Revisa que estimadores corrieron y si sus senales diagnosticas coinciden.'],['Triage operacional','Recomienda CPU / tensor-network / HPC primero / QPU despues bajo proxies medidos.']];
  return '<details class=adv><summary>'+(EN?'How the verdict is produced':'Como se produce el veredicto')+'</summary><div class=method-grid>'+steps.map(function(s,i){return'<div class=pipe><div class=pipe-num>'+(i+1)+'</div><div><div class=pipe-t>'+s[0]+'</div><div class=pipe-d>'+s[1]+'</div></div></div>';}).join('')+'</div></details>';
}
function compareHTML(){var EN=LANG==='en';var rows=EN?[['Tool','Exact simulation','Simulatability diagnostics'],['Stim','Yes, Clifford/stabilizer','Limited'],['Qiskit','Sometimes, statevector/noisy','No'],['quimb / cotengra','Tensor contraction','Partial'],['Atlas','Not the main goal','Yes: multi-metric diagnostics']]:[['Herramienta','Simulacion exacta','Diagnostico de simulabilidad'],['Stim','Si, Clifford/stabilizer','Limitado'],['Qiskit','A veces, statevector/ruido','No'],['quimb / cotengra','Contraccion tensorial','Parcial'],['Atlas','No es el objetivo principal','Si: diagnostico multi-metrica']];
  return '<details class=adv><summary>'+(EN?'Why this tool exists':'Por que existe esta herramienta')+'</summary><div class=compare-grid>'+rows.map(function(r,i){return'<div class=compare-row><span>'+(i?'<b>'+r[0]+'</b>':r[0])+'</span><span>'+r[1]+'</span><span>'+r[2]+'</span></div>';}).join('')+'</div></details>';
}
// Evidence Ledger (pedido en auditoría): tabla auditable por métrica — valor · método ·
// exacto/heurístico · si gobernó el veredicto. Convierte "demo" en evidencia trazable.
function evidenceLedger(o){var EN=LANG==='en',c=o.costs_log2||{},ra=o.route_adjudication||{},
  gov=String(ra.governing_estimator||o.best_method||'').toLowerCase(),
  trunc=o.mps_truncated||(o.ground_truth&&o.ground_truth.validations&&o.ground_truth.validations.mps_truncated),
  twx=o.treewidth_exact,sp=c['spread(local)'];
  function hit(k){return gov.indexOf(k)>=0;}
  var HI=EN?'HIGH':'ALTO',LO=EN?'low':'bajo';
  var rows=[
    ['#T '+(EN?'(magic)':'(magia)'),o.t_count,'parser',EN?'exact':'exacto',(hit('magic')||hit('fold'))?HI:(EN?'med':'medio')],
    ['MPS bond',(trunc?'≥':'')+'2^'+c['MPS(entangle)'],'quimb',trunc?(EN?'lower bound (truncated)':'cota inf. (truncado)'):(EN?'measured (exact)':'medido (exacto)'),(hit('mps')||hit('entangle'))?HI:LO],
    ['treewidth','2^'+c['contraction(treewidth)'],'cotengra',twx?(EN?'exact (optimal)':'exacto (óptimo)'):(EN?'greedy upper bound':'cota sup. greedy'),(hit('treewidth')||hit('contraction'))?HI:LO],
    ['spread',sp==null?'n/a':'2^'+sp,'pauli-prop',(o.spread_state||(sp==null?'not_used':'computed')).replace(/_/g,' '),hit('spread')?HI:(sp==null?'—':LO)],
    (function(){var pr=o.entanglement_profile;
      if(pr){var asym=pr.asymmetry>0.5,perm=pr.permutation_camouflage;  // cortes contiguos + biparticiones arbitrarias (anti S-spoofing / MPS-camouflage)
        var flag=perm?(EN?'PERM-CAMOUFLAGE ⚠':'PERM-CAMUFLAJE ⚠'):(asym?(EN?'ASYMMETRY ⚠':'ASIMETRÍA ⚠'):(EN?'check':'verif.'));
        return [(EN?'S max (cuts+perms)':'S max (cortes+perm)'),pr.s_max+' nats'+((asym||perm)?' ⚠':''),'statevector',
          (EN?'exact; n/2='+pr.s_half+' contig-max='+pr.s_max_contig:'exacto; n/2='+pr.s_half+' contig-max='+pr.s_max_contig),flag];}
      return ['S (n/2)',o.entanglement_entropy!=null?o.entanglement_entropy+' nats':'n/a','statevector',o.entanglement_entropy!=null?(EN?'exact (n≤14)':'exacto (n≤14)'):'n/a',EN?'check':'verif.'];})()];
  var th=EN?['Metric','Value','Method','Type','Drove verdict']:['Métrica','Valor','Método','Tipo','Gobernó'];
  var head='<tr>'+th.map(function(h){return '<th style="text-align:left;padding:4px 8px;color:var(--text3);font:700 9px IBM Plex Sans;text-transform:uppercase;letter-spacing:.05em">'+h+'</th>';}).join('')+'</tr>';
  var body=rows.map(function(r){var imp=r[4],gov=imp===HI,col=gov?'#22C55E':'var(--text3)';return '<tr style="border-top:1px solid var(--bd)'+(gov?';background:rgba(34,197,94,.06)':'')+'">'+
    '<td style="padding:5px 8px;color:var(--text2);font:600 11px IBM Plex Sans">'+r[0]+'</td>'+
    '<td style="padding:5px 8px;color:var(--text);font:700 12px JetBrains Mono">'+r[1]+'</td>'+
    '<td style="padding:5px 8px;color:var(--text3);font:11px JetBrains Mono">'+r[2]+'</td>'+
    '<td style="padding:5px 8px;color:var(--text3);font-size:10px">'+r[3]+'</td>'+
    '<td style="padding:5px 8px;color:'+col+';font:700 10px JetBrains Mono">'+(gov?'● '+(EN?'GOVERNED':'GOBERNÓ'):imp)+'</td></tr>';}).join('');
  return '<details class=adv open><summary>'+(EN?'Evidence Ledger — what was measured, how, and whether it drove the verdict':'Evidence Ledger — qué se midió, cómo, y si gobernó el veredicto')+'</summary>'+
    '<table style="width:100%;border-collapse:collapse;margin:4px 0 6px;table-layout:auto">'+head+body+'</table>'+
    '<div style="font-size:10px;color:var(--text3);padding:0 8px 9px;line-height:1.4">'+(EN?'Governing estimator: ':'Estimador gobernante: ')+'<b style="color:var(--accent)">'+(ra.governing_estimator||o.best_method||'n/a')+'</b> → '+(EN?'route ':'ruta ')+'<b>'+(ra.route||'n/a')+'</b>. '+(EN?'exact = measured/optimal; greedy/lower-bound = conservative (does not overclaim).':'exacto = medido/óptimo; greedy/cota-inferior = conservador (no sobre-clama).')+'</div></details>';}
function evidenceHTML(o){var EN=LANG==='en',gt=o.ground_truth&&o.ground_truth.methods?o.ground_truth.methods:{},V=o.ground_truth&&o.ground_truth.validations?o.ground_truth.validations:{},ra=o.route_adjudication||{};return '<details class=adv><summary>'+(EN?'Evidence / method coverage':'Evidencia / cobertura de metodos')+'</summary><div class=evidence>'+(EN?'Estimator availability':'Disponibilidad de estimadores')+': <b>Stim '+(gt.stim?'✓':'-')+'</b> · <b>quimb '+(gt.quimb?'✓':'-')+'</b> · <b>cotengra '+(gt.cotengra?'✓':'-')+'</b> · <b>Pauli '+(gt.pauli?'✓':'-')+'</b><br>'+(EN?'MPS/treewidth consistency':'Consistencia MPS/treewidth')+': <b>'+(V.mps_tw_consistency||'n/a')+'</b> · '+(EN?'MPS truncated':'MPS truncado')+': <b>'+(V.mps_truncated?'yes (lower bound)':'no')+'</b><br>'+(EN?'Backend route adjudicator':'Adjudicador backend de ruta')+': <b>'+(ra.route||'n/a')+'</b> via <b>'+(ra.governing_estimator||'n/a')+'</b> · '+(EN?'confidence':'confianza')+' <b>'+((ra.confidence&&ra.confidence.score)||'n/a')+'</b><br>'+(EN?'Measured-oracle route benchmark':'Benchmark de ruta con oraculo medido')+' ('+(EN?'2517 certified circuits':'2517 circuitos certificados')+'): <b>'+(EN?'Atlas route-correctness 2506/2517 = 0.996 (11 disagreements: 1 false-safety + 10 safe-direction under-routes), 0 false-alarm':'Atlas route-correctness 2506/2517 = 0.996 (11 desacuerdos: 1 falsa-seguridad + 10 sub-rutas en direccion segura), 0 falsa-alarma')+'</b> '+(EN?'vs single-estimator (800-slice)':'vs estimador-unico (corte 800)')+' <b>'+(EN?'treewidth-only 166 false-alarm · MPS-only 16 false-safety · magic-only 8 FS+96 FA':'treewidth-only 166 falsa-alarma · MPS-only 16 falsa-seguridad · magic-only 8 FS+96 FA')+'</b>; '+(EN?'the multi-method min-over-estimators is what avoids the single-method failures':'el min multi-metodo es lo que evita los fallos de un solo metodo')+'<br>'+(EN?'Counterexamples':'Contraejemplos')+': <b>mps_chain_30_deep</b> '+(EN?'beats treewidth-only; ':'vence treewidth-only; ')+'<b>grid_5x5_25_dense</b> '+(EN?'catches MPS lower-bound false safety.':'detecta falsa seguridad por MPS truncado.')+'<br>'+(EN?'Analytic physics checks':'Chequeos fisicos analiticos')+': <b>'+(o.phys_selftest&&o.phys_selftest.all_ok?'Bell/GHZ/product OK':'n/a')+'</b><br>'+(EN?'Publication benchmark':'Benchmark de publicacion')+': <b>python3 engine/atlas_benchmark_bundle.py</b> → corpus SHA + confusion matrix + metric definition</div></details>';}
function causalChainHTML(o,av){var EN=LANG==='en',c=o.costs_log2||{},V=o.ground_truth&&o.ground_truth.validations?o.ground_truth.validations:{},mps=c['MPS(entangle)'],tw=c['contraction(treewidth)'],sp=c['spread(local)'];
  var ra=o.route_adjudication||null;
  if(ra){
    var inv=(ra.invalidated_estimators||[]).map(function(x){return '<div class=leaf><span>'+x.estimator+' · '+x.observed+'</span><b>'+x.reason+'</b></div>';}).join('');
    var cf=(ra.counterfactuals||[]).map(function(x){return '<div class=leaf><span>'+x.baseline+' · '+x.failure_mode+'</span><b>'+x.why_atlas_differs+'</b></div>';}).join('');
    return '<div class=score-tree><div class=root>'+(EN?'Backend route adjudication':'Adjudicacion backend de ruta')+': '+ra.route+' via '+ra.governing_estimator+'</div>'+
      '<div class=leaf><span>'+(EN?'governing cost':'coste gobernante')+' · 2^'+ra.governing_cost_log2+'</span><b>'+ra.governing_reason+'</b></div>'+
      inv+cf+'</div>';
  }
  var rows=[];
  if(V.mps_truncated){
    rows.push([EN?'MPS observed':'MPS observado','>= 2^'+mps,EN?'lower bound only; cannot govern final route':'solo cota inferior; no puede gobernar la ruta final']);
    rows.push(['treewidth','2^'+tw,tw>=30?(EN?'governing estimator: classical route needs HPC/escalation review':'estimador gobernante: ruta clasica requiere revision HPC/escalamiento'):(EN?'budget check required':'requiere contraste con presupuesto')]);
  }else if(av.tract&&/MPS/.test(o.best_method||'')){
    rows.push(['MPS','2^'+mps,EN?'exact/non-truncated route found by quimb':'ruta exacta/no truncada encontrada por quimb']);
    rows.push(['treewidth','2^'+tw,EN?'not governing because cheaper MPS route exists':'no gobierna porque existe ruta MPS mas barata']);
  }else if(av.tract&&/spread/.test(o.best_method||'')){
    rows.push(['Pauli spread',sp==null?'n/a':'2^'+sp,EN?'local operator growth bounds the route':'crecimiento local del operador acota la ruta']);
    rows.push(['MPS / TW','2^'+mps+' / 2^'+tw,EN?'secondary checks':'chequeos secundarios']);
  }else{
    rows.push([EN?'governing estimator':'estimador gobernante',o.best_method||'n/a',o.verdict||'']);
    rows.push(['MPS / TW','2^'+mps+' / 2^'+tw,EN?'compare routes, do not average them':'comparar rutas, no promediarlas']);
  }
  return '<div class=score-tree><div class=root>'+(EN?'Causal route decision':'Decision causal de ruta')+'</div>'+rows.map(function(r){return '<div class=leaf><span>'+r[0]+' · '+r[1]+'</span><b>'+r[2]+'</b></div>';}).join('')+'</div>';}
function scopeHTML(){var EN=LANG==='en',rows=EN?[
  ['ok','Validated on QPU','Classical route reproduces real hardware','On ibm_kingston (Heron r2, 2026-06-22): Atlas-CPU circuits ghz4 / cliffordT5 give TVD(ideal, QPU) ≈ 0.059 / 0.055 — the exact classical distribution reproduces the noisy device within error ⇒ "you don\'t need the QPU" validated end-to-end on metal. Embedding A/B: same GHZ4 is 7.3× worse routed through the TLS cluster. See benchmarks/QPU_RESULTS.md.'],
  ['ok','Supported','Quantum compute triage','The UI shows measured proxies, cross-check methods, confidence, and a recommended compute path before QPU spend.'],
  ['ok','Supported','Classical simulability','For this circuit, Atlas reports whether available classical routes look practical under Pauli spread / MPS / treewidth diagnostics.'],
  ['lim','Limited','Predicts simulation cost','Only proxy estimates and measured small-circuit timings are shown; no universal cost prediction is claimed.'],
  ['no','Not claimed','Identifies quantum advantage','Atlas may flag QPU/HPC candidates, but it does not certify quantum advantage.'],
  ['no','Not claimed','Impossible circuits','“Intractable” means outside declared classical budgets/proxies, not a mathematical impossibility proof.']
]:[
  ['ok','Validado en QPU','La ruta clásica reproduce el hardware real','En ibm_kingston (Heron r2, 2026-06-22): los circuitos Atlas-CPU ghz4 / cliffordT5 dan TVD(ideal, QPU) ≈ 0.059 / 0.055 — la distribución clásica exacta reproduce al device ruidoso dentro del error ⇒ "no necesitas el QPU" validado end-to-end en hardware real. A/B de embedding: el mismo GHZ4 es 7.3× peor ruteado por el cluster TLS. Ver benchmarks/QPU_RESULTS.md.'],
  ['ok','Soportado','Triage de computo cuantico','La UI muestra proxies medidos, metodos de cruce, confianza y una ruta de computo recomendada antes de gastar QPU.'],
  ['ok','Soportado','Simulabilidad clasica','Para este circuito, Atlas reporta si las rutas clasicas parecen practicas bajo diagnosticos de Pauli spread / MPS / treewidth.'],
  ['lim','Limitado','Predice coste de simulacion','Solo se muestran proxies y tiempos medidos en circuitos pequenos; no se reclama prediccion universal de coste.'],
  ['no','No reclamado','Identifica ventaja cuantica','Atlas puede marcar candidatos QPU/HPC, pero no certifica ventaja cuantica.'],
  ['no','No reclamado','Circuitos imposibles','“Intractable” significa fuera de presupuestos/proxies declarados, no prueba matematica de imposibilidad.']
];
  return '<details class=adv open><summary>'+(EN?'Scientific scope: what Atlas can demonstrate':'Alcance cientifico: que puede demostrar Atlas')+'</summary><div class=scope-grid>'+rows.map(function(r){return'<div class=scope-row><div class="scope-tag '+r[0]+'">'+r[1]+'</div><div><div class=scope-claim>'+r[2]+'</div><div class=scope-proof>'+r[3]+'</div></div></div>';}).join('')+'</div></details>';
}
function showResult(o){window.lastAtlas=o;o._econBase=o.econ;if(o.econ)o.econ=recomputeEcon(o.econ,ASSUMP);if(typeof updateStepper==='function')setTimeout(updateStepper,0);
  let w=(o.verdict||'').includes('WALL')||(o.verdict||'').includes('nucleo');
  var pw=function(v){return v==null?'n/a':'2^'+v;};
  var av=atlasVerdict(o);
  // B-1/B-2 (audit): cuando el metodo elegido es una COTA INFERIOR truncada, el numero reportado es un PISO,
  // no el coste real. El honesto es contrastarlo con el unico estimador no-truncado (treewidth) y avisar.
  var _prov=/PROVISIONAL|TRUNCAD|cota inferior|lower bound/i.test(o.verdict||'');
  var _mps=o.costs_log2?o.costs_log2['MPS(entangle)']:null,_tw=o.costs_log2?o.costs_log2['contraction(treewidth)']:null;
  var _lb=(_prov&&_tw!=null)?`<div class=warn style="margin-top:8px;border-color:rgba(248,113,113,.35);background:rgba(248,113,113,.07)"><b>⚠ ${LANG==='en'?'Lower bound, not a verdict':'Cota inferior, no un veredicto'}:</b> ${LANG==='en'?'the chosen method (MPS) is TRUNCATED — its 2^'+_mps+' is a FLOOR, not the achievable cost. The only untruncated estimate is treewidth 2^'+_tw+'.':'el método elegido (MPS) está TRUNCADO — su 2^'+_mps+' es un PISO, no el coste alcanzable. El único estimador no-truncado es treewidth 2^'+_tw+'.'} ${(_tw>=30)?(LANG==='en'?'<b>2^'+_tw+' exceeds any classical budget → treat as INTRACTABLE.</b>':'<b>2^'+_tw+' supera cualquier presupuesto clásico → trátalo como INTRACTABLE.</b>'):(LANG==='en'?'Check 2^'+_tw+' against your budget.':'Contrasta 2^'+_tw+' con tu presupuesto.')}</div>`:'';
  // #67: dropped / out-of-range instructions are surfaced PROMINENTLY (not buried),
  // and the verdict explicitly states it was computed without them.
  var _parseWarn=(o.warnings&&o.warnings.length)?`<div class=warn style="margin:0 0 10px;border:1px solid rgba(248,113,113,.5);background:rgba(248,113,113,.12);color:#fecaca;font-weight:600"><b>⚠ ${LANG==='en'?o.warnings.length+' invalid instruction(s) ignored':o.warnings.length+' instrucción(es) inválida(s) ignorada(s)'}:</b> ${o.warnings.map(function(x){return x.replace(/</g,'&lt;');}).join('; ')}. <b>${LANG==='en'?'The verdict below was computed WITHOUT them.':'El veredicto de abajo se calculó SIN ellas.'}</b></div>`:'';
  var noiseEs='Nota: veredicto para el circuito COHERENTE (sin ruido). El ruido real suele hacer el circuito MAS simulable clasicamente, asi que un veredicto duro es COTA SUPERIOR de la dureza en hardware.';
  var noiseEn='Note: diagnostic is for the COHERENT (noiseless) circuit. Real noise tends to make a circuit MORE classically simulable, so a high index is an UPPER BOUND on hardware behavior.';
  var rec=atlasRecommendation(o,av),why=explainWhy(o,av);
  var _mpsLabel=(_prov?'>= ':'')+pw(o.costs_log2['MPS(entangle)']);
  var fm=o.family_meta||null,diag=(LANG==='en'?'Measured diagnostics':'Diagnosticos medidos')+': #T '+(o.t_count||0)+' · MPS '+_mpsLabel+' · TW '+pw(o.costs_log2['contraction(treewidth)'])+' · spread '+pw(o.costs_log2['spread(local)']);
  var _fd=fm?(fm.requested_interaction_density!=null?fm.requested_interaction_density:fm.requested_core_density):null;
  var famHTML=fm?'<div class=warn style="margin:0 0 12px;color:#94a3b8"><b>'+(LANG==='en'?'Requested family':'Familia solicitada')+':</b> '+fm.family_type+' · '+fm.topology+' · magic '+fm.requested_magic+' · spread '+fm.requested_spread+' · interaction density '+_fd+' · seed '+fm.seed+'<br><b>'+diag+'</b><br><b>'+(LANG==='en'?'Triage result':'Resultado de triage')+':</b> '+(o.verdict||'')+((/Challenge|Stress|Critical/.test(fm.family_type)&&av.tract)?'<br><span class=ok>'+(LANG==='en'?'Hardness challenge rejected: Atlas found a practical classical route under measured diagnostics.':'Reto de dureza rechazado: Atlas encontro una ruta clasica practica bajo los diagnosticos medidos.')+'</span>':'')+'</div>':'';
  var explorerHTML='<div class=diag-explorer>'+designExplorerHTML()+'</div>';   // V2 fix: el mapa vive siempre en diag-explorer (workspace Explore lo posee), en cualquier modo
  let html=`<div class=diag-grid><div class=diag-primary><div class="answer-card" data-route="${(av.answer||'').toLowerCase().replace(/[^a-z]/g,'')}"><div class=answer-q>VEREDICTO DE CÓMPUTO</div>
    ${_parseWarn}${_lb}
    <div class=answer-main><div class="answer-badge ${av.cls}">${av.answer}</div><div><div class=answer-title>${av.title}</div><div class=answer-sub>${av.reason}</div></div></div>
    <button class=triage-cta onclick="buildDecisionPanel();var p=$('decision-panel');if(p){p.classList.add('open');if(p.scrollIntoView)p.scrollIntoView({behavior:'smooth'});}">
      <span class=triage-cta-k>${LANG==='en'?'Recommended next step':'Accion recomendada'}</span>
      <span class=triage-cta-main>→ ${rec.title}</span>
      <span class=triage-cta-go>${LANG==='en'?'Decide route':'Decidir ruta'} →</span></button>
    ${causalChainHTML(o,av)}
    <div class=score-row><div class=score-label>${LANG==='en'?'Heuristic index':'Indice heuristico'}</div><div class=score-track><div class=score-pin style="left:${av.score}%"></div></div><div class=score-num>${av.score}/100</div></div>
    <div class=score-scale><span>0-30 CPU</span><span>30-60 Tensor</span><span>60-80 HPC review</span><span>80-100 Escalate</span></div>
    ${scoreTreeHTML(av)}
    <div class=answer-grid><div class=answer-kv><div class=answer-k>${LANG==='en'?'Status':'Estado'}</div><div class=answer-v>${av.band}</div></div><div class=answer-kv><div class=answer-k>${LANG==='en'?'Method footprint':'Footprint del metodo'}</div><div class=answer-v>${av.memory}</div></div><div class=answer-kv><div class=answer-k>${LANG==='en'?'Confidence':'Confianza'}</div><div class="answer-v small">${av.confidence}</div></div></div>
    <div class=answer-kv style="margin-top:8px;grid-column:1/-1;border-top:1px solid var(--bd);padding-top:8px"><div class=answer-k>${LANG==='en'?'Certified target (what this verdict certifies)':'Objetivo certificado (que certifica este veredicto)'}</div><div class="answer-v small" style="line-height:1.4">${av.certifiedTarget}</div></div></div>${famHTML}</div>${explorerHTML}</div>
    <div class=recommend><div class="rec-card primary"><div class=rec-h>${LANG==='en'?'Recommended action':'Accion recomendada'}</div><div class=rec-main>${rec.title}</div><div class=rec-list>${rec.items.map(function(x){return'<span>'+x+'</span>';}).join('')}</div></div><div class=rec-card><div class=rec-h>${LANG==='en'?'Decision target':'Objetivo de decision'}</div><div class=rec-main>${LANG==='en'?'Do not optimize metrics; choose compute path.':'No optimizar metricas; elegir ruta de computo.'}</div><div class=rec-list><span>${av.question}</span><span>${LANG==='en'?'Answer: ':'Respuesta: '}${av.answer}</span></div></div></div>
    <div class=why-card><div class=why-title>${why.label}</div><div class=why-main>${why.main}</div><div class=why-grid><div class=why-m><div class=why-k>${why.k1}</div><div class=why-v>${why.v1}</div><div class=why-d>${why.detail}</div></div><div class=why-m><div class=why-k>${why.k2}</div><div class=why-v>${why.v2}</div><div class=why-d>${LANG==='en'?'Observed from this circuit.':'Observado en este circuito.'}</div></div><div class=why-m><div class=why-k>${LANG==='en'?'threshold':'umbral'}</div><div class=why-v>${why.threshold}</div><div class=why-d>${LANG==='en'?'Above this, the route changes.':'Por encima de esto cambia la ruta.'}</div></div></div></div>
    ${evidenceLedger(o)}
    <div class=primary-actions><button class="tool hero" onclick="buildDecisionPanel();document.getElementById('decision-panel').classList.add('open')">${LANG==='en'?'What should I do?':'¿Que debo hacer?'}</button><button class=tool onclick="exportReport()">${LANG==='en'?'Export report':'Exportar reporte'}</button><button class=tool onclick="genReroll()">${LANG==='en'?'Generate harder variant':'Generar variante'}</button></div>
    <details class=adv><summary>${LANG==='en'?'Advanced metrics':'Metricas avanzadas'}</summary><div class=chips style="padding:0 12px 12px">
      <span class="chip c-magic">#T <b>${o.t_count}</b></span><span class="chip c-libro">${LANG==='en'?'structure':'estructura'} <b>${structureLabel(o.libro_flattener)}</b></span>
      <span class="chip c-mps">MPS ${_mpsLabel}</span><span class="chip c-spread">spread ${pw(o.costs_log2['spread(local)'])}</span>
      <span class="chip c-tw">treewidth ${pw(o.costs_log2['contraction(treewidth)'])}</span><span class="chip c-libro">${o.verdict}</span></div></details>
    ${scopeHTML()}${methodHTML()}${compareHTML()}${evidenceHTML(o)}
    <div class=noise-box><div class=noise-head><span class=nchev onclick="toggleNoise(this)" title="Mostrar/ocultar detalle">▾</span><span data-i18n=noiseHead>${LANG==='en'?'Noise (2q depolarizing)':'Ruido (depolarizante 2q)'}</span><label class=sr-only for=noise-p>${LANG==='en'?'2-qubit depolarizing error rate (0 to 5%)':'Tasa de error depolarizante de 2 qubits (0 a 5%)'}</label><input type=range id=noise-p min=0 max=50 step=1 value=5 oninput="renderNoise()" aria-label="${LANG==='en'?'Depolarizing error rate':'Tasa de error depolarizante'}"><output for=noise-p id=noise-pl class=noise-pl>0.5%</output></div><div id=noise-out class=noise-out></div></div>
    <div class=warn style="margin-top:8px;color:#64748b" data-i18n=noise>${LANG==='en'?noiseEn:noiseEs}</div>
    ${(o.warnings&&o.warnings.length)?'<div class=warn>⚠ '+o.warnings.map(x=>x.replace(/</g,'&lt;')).join('<br>⚠ ')+'</div>':''}`;
  let circHtml=`<div class=circ-head><span data-i18n=tabCirc>${LANG==='en'?'Circuit':'Circuito'}</span> <span style="font-size:10px;color:var(--text3);font-weight:400" title="${LANG==='en'?'Rendered from the QASM normalized by Atlas (gate set mapped + flattened via Qiskit); order may differ from the editor but is semantically equivalent.':'Renderizado del QASM normalizado por Atlas (conjunto de puertas mapeado + aplanado vía Qiskit); el orden puede diferir del editor pero es semánticamente equivalente.'}">· ${LANG==='en'?'normalized QASM':'QASM normalizado'}</span> <button class=playbtn id=playbtn onclick="playLast()" data-i18n=btnPlay>${LANG==='en'?'♪ Play':'♪ Reproducir'}</button><button class=playbtn id=expbtn onclick="exportLast()" title="Descarga el sonido del circuito como WAV (incluye el ruido del slider)">⤓ WAV</button><label class=loopl>×<input id=audio-loops type=number min=1 max=64 value=1 onchange="updLoops()"> <span id=loopsec></span></label></div><div id=circ-inline></div>`;
  var ps=$('pSummary'),pr=$('pResultado'),br=$('bResultado');
  if(ps)ps.innerHTML=html;if(pr)pr.innerHTML=circHtml;if(br)br.style.display='inline-block';
  if(typeof buildDecisionPanel==='function')buildDecisionPanel();   // #17/#21/#29: keep central + lateral in sync atomically (same circuit)
  var gt=o.ground_truth,xv='';
  if(gt&&gt.validations){var V=gt.validations,bad=function(x){return x&&x!=='ok'&&x!==false;};
    xv=`\n<span class=k>multi-method consistency (cobertura y acuerdo de estimadores):</span>\n`+
      `  #T vs Stim         : ${V.tcount_vs_stim==='ok'?'<span class=ok>coinciden ✓</span>':'<span class=warn2>'+V.tcount_vs_stim+'</span>'}\n`+
      (V.magic_exact?`  [self-test motor] magia exacta n≤6: ${/ok/.test(V.magic_exact)?'<span class=ok>'+V.magic_exact+'</span>':'<span class=warn2>'+V.magic_exact+' (unitario Clifford)</span>'} <span class=k>(capacidad del estimador, no veredicto de este circuito)</span>\n`:'')+
      `  MPS vs treewidth   : ${V.mps_tw_consistency==='ok'?'<span class=ok>consistente ✓</span>':'<span class=warn2>'+V.mps_tw_consistency+'</span>'}\n`+
      `  treewidth          : ${V.treewidth_exact?'<span class=ok>OPTIMO EXACTO ✓</span>':'cota superior heuristica'}\n`+
      `  MPS truncado       : ${V.mps_truncated?'<span class=warn2>SI -> coste MPS es cota INFERIOR</span>':'<span class=ok>no (bond exacto)</span>'}\n`+
      `  metodos corridos   : Stim ${gt.methods.stim?'✓':'✗'} · quimb ${gt.methods.quimb?'✓':'✗'} · cotengra ${gt.methods.cotengra?'✓':'✗'} · pauli ${gt.methods.pauli?'✓':'✗'}`;}
  var EN2=LANG==='en',pinv='';                          // F-1: invariante FISICO ANALITICO (no coste)
  if(o.phys_selftest){var st=o.phys_selftest;
    pinv='\n<span class=k>'+(EN2?'PHYSICAL invariant (observable, not cost):':'invariante FISICO (observable, no coste):')+'</span>\n'+
      '  [self-test motor] S(Bell)=ln2='+st.ln2+(st.all_ok?'  <span class=ok>'+st.checks.length+(EN2?' canonical states OK (Bell/GHZ/product) — engine reference, not this circuit':' estados canonicos OK (Bell/GHZ/producto) — referencia del motor, no este circuito')+'</span>':'  <span class=warn2>'+(EN2?'FAIL':'FALLO')+'</span>')+'\n'+
      (o.entanglement_entropy!=null?('  S('+(EN2?'this circuit, cut n/2':'este circuito, corte n/2')+')='+o.entanglement_entropy+(EN2?' nats  <span class=ok>[exact statevector]</span>':' nats  <span class=ok>[statevector exacto]</span>')):
       o.entanglement_skipped?('  S='+(EN2?'n/a (unsupported gates: ':'n/a (gates no soportados: ')+o.entanglement_skipped.join(',')+')'):
       ('  S='+((o.n||0)>14?(EN2?'n/a (n='+o.n+'>14: exact statevector only n<=14)':'n/a (n='+o.n+'>14: statevector exacto solo n<=14)'):(EN2?'n/a (not computed for this circuit)':'n/a (no computado para este circuito)'))));
    if(o.magic_check){var mc=o.magic_check,mmsg;             // magia del ESTADO (M2) vs sintaxis (T-count): NO redundante
      if(mc.consistent)mmsg='<span class=ok>'+(EN2?'consistent ✓ (independent physical check)':'consistente ✓ (chequeo fisico independiente)')+'</span>';
      else if(!mc.state_is_magic&&mc.syntax_T>0)mmsg='<span class=ok>'+(EN2?'state is Clifford → the T-gates net to Clifford; #T is an UPPER bound ✓':'el estado es Clifford → las T netas se cancelan; #T es cota SUPERIOR ✓')+'</span>';
      else mmsg='<span class=warn2>'+(EN2?'⚠ magic without T — review':'⚠ magia sin T — revisar')+'</span>';
      pinv+='\n  '+(EN2?'magic from STATE':'magia del ESTADO')+': M2='+mc.M2+' vs #T='+mc.syntax_T+(EN2?' (syntax)':' (sintaxis)')+'  '+mmsg;}}
  var lb=$('logbody');if(lb)lb.innerHTML=`<span class=k>analisis completo</span>\nmagia(#T) = ${o.t_count}  <span class=ok>[conteo exacto del parser · Stim valida checks Clifford, NO simula las T]</span>\n`+
    `estructura = ${structureLabel(o.libro_flattener)}  [flattener]\nMPS bond = ${_prov?'>= ':''}2^${o.costs_log2['MPS(entangle)']}  <span class=ok>[${o.gt_ok?'quimb (real)':'arsenal'}]</span>\n`+
    `treewidth = 2^${o.costs_log2['contraction(treewidth)']}  <span class=ok>[${o.gt_ok?'cotengra (cota sup. heuristica)':'arsenal'}]</span>\n`+
    `spread = ${o.costs_log2['spread(local)']==null?((o.n||0)>14?(LANG==='en'?'n/a (n='+o.n+'>14: pauli-prop only n<=14)':'n/a (n='+o.n+'>14: pauli-prop solo n<=14)'):(LANG==='en'?'n/a (not used for this circuit; verdict from MPS/treewidth)':'n/a (no usado para este circuito; veredicto por MPS/treewidth)')):'2^'+o.costs_log2['spread(local)']}  [pauli-prop]\nveredicto = ${o.verdict}`+xv+pinv+
    `${(o.cross_warnings&&o.cross_warnings.length)?'\n<span class=warn2>⚠ '+o.cross_warnings.map(x=>x.replace(/</g,'&lt;')).join('\n⚠ ')+'</span>':''}`;
  metrics(o);if($('phase')){renderPhaseDots();phaseMode(phaseView||'2d');
    animatePhaseRun(($('qasm')&&$('qasm').value)||'',o);}
  saveHistory(o,av);
  renderNoise();                                                     // rango [ruidoso, coherente]
  if(o.circuit){drawCircuit(o.n||8,o.circuit,'pCircuito');drawCircuit(o.n||8,o.circuit,'circ-inline');updLoops();}  // inline en Resultado + pestaña
  if(o.qasm_in){var pq=$('pQASM'),bq=$('bQASM');if(pq)pq.innerHTML='<pre>'+o.qasm_in.replace(/</g,'&lt;')+'</pre>';if(bq)bq.style.display='inline-block';}}  // Bug II: QASM tab refleja el circuito analizado

async function analyze(){let v=$('qasm').value.trim();if(!v){resetDiagnostics();return}
  var is3=/OPENQASM\s+3|qubit\s*\[/i.test(v),fm=$('fmt');if(fm)fm.textContent='OpenQASM '+(is3?'3.0':'2.0');  // badge dinamico
  var ab=$('analyzebtn'),t0=performance.now();
  if(ab){ab.disabled=true;ab.setAttribute('aria-busy','true');ab.classList.add('busy');ab._html=ab.innerHTML;ab.innerHTML='<span class=btn-spinner></span> '+(LANG==='en'?'Analyzing…':'Analizando…');}  // D1 capa 1
  $('pSummary').innerHTML='<div class="verd loading"></div><div class="verd loading" style="margin-top:8px;height:80px"></div>';  // D1 capa 2 skeleton
  $('st').innerHTML='<span class=spin>&#9679;</span> '+(LANG==='en'?'Analyzing…':'Analizando…');
  try{let o=await post('/api/diagnose',{qasm:v});
    var dt=((performance.now()-t0)/1000).toFixed(2);
    if(o.error){$('pSummary').innerHTML=`<div class="verd w"><span class=ico>⚠</span><span class=tx>${o.error}</span></div>`;$('st').innerHTML='&#9679; Error'}
    else{showResult(o);$('st').innerHTML='<span class=g>&#9679; '+(LANG==='en'?'Done in ':'Listo en ')+dt+'s</span>';afterResult();}}
  catch(e){$('pSummary').innerHTML=`<div class="verd w"><span class=ico>⚠</span><span class=tx>${(e&&e.message)||e}</span></div>`;$('st').innerHTML='&#9679; Error'}
  finally{restoreAnalyzeButton(ab);}}  // D1 capa 3
function afterResult(){                                  // R2: el panel de decision se hace prominente tras analizar
  var tg=$('decision-toggle');if(tg)tg.classList.add('has-result');
  // auto-abrir en desktop: la decision es la salida principal, no un panel oculto.
  if(window.innerWidth>860){var p=$('decision-panel');
    if(p&&!p.classList.contains('open')){buildDecisionPanel();p.classList.add('open');if(tg)tg.setAttribute('aria-expanded','true');}
    try{localStorage.setItem('atlas-dp-seen','1');}catch(e){}}}
var genSeed=0;                                            // FE-3: seed del generador (el dado 🎲 lo varia)
async function genAt(magic,spread,book,meta){$('st').innerHTML='&#9679; '+(LANG==='en'?'Generating...':'Generando...');
  let o=await post('/api/generate',{magic,spread,book,treewidth:dials.Tw,n:+($('gn').value||12),seed:genSeed});
  if(o.error){$('st').innerHTML='&#9679; '+o.error;return}
  o.family_meta=meta||lastFamilyMeta||familyMeta(+magic||0,+spread||0,coreDensityFor(+magic||0,+spread||0),genSeed);
  $('qasm').value=o.qasm;onInput();clearTimeout(window._t);if(curMode==='gen')ensureGenExplorer();else mode('dx');showResult(o);          // o ya trae el resultado: sin re-analizar
  $('st').innerHTML='<span class=g>&#9679; '+(LANG==='en'?'Generated (seed '+genSeed+')':'Generado (seed '+genSeed+')')+'</span>';}
function genReroll(){genSeed=(genSeed+1)%100000;genFromPanel();}      // 🎲 nuevo circuito con los mismos dials
function easyExample(){dials.Tw='low';if($('gn'))$('gn').value=8;genAt('low','low','free');}
// Bug#5/#7: construye un 2D-denso DETERMINISTA en JS (sin depender del gen del servidor, que
// fallaba silenciosamente). Siempre carga, instantaneo, y es genuinamente duro (grilla 5x5 + T).
function buildHardDemo(){var R=5,C=5,n=R*C,L=['OPENQASM 2.0;','include "qelib1.inc";','qreg q['+n+'];'];
  var idx=function(r,c){return r*C+c;};
  for(var i=0;i<n;i++)L.push('h q['+i+'];');
  for(var d=0;d<6;d++){
    for(var r=0;r<R;r++)for(var c=0;c<C-1;c+=2)L.push('cx q['+idx(r,c)+'],q['+idx(r,c+1)+'];');   // horizontal A
    for(var r2=0;r2<R-1;r2+=2)for(var c2=0;c2<C;c2++)L.push('cx q['+idx(r2,c2)+'],q['+idx(r2+1,c2)+'];'); // vertical A
    for(var i2=0;i2<n;i2+=2)L.push('t q['+i2+'];');
    for(var r3=0;r3<R;r3++)for(var c3=1;c3<C-1;c3+=2)L.push('cx q['+idx(r3,c3)+'],q['+idx(r3,c3+1)+'];'); // horizontal B
    for(var r4=1;r4<R-1;r4+=2)for(var c4=0;c4<C;c4++)L.push('cx q['+idx(r4,c4)+'],q['+idx(r4+1,c4)+'];'); // vertical B
  }
  return L.join('\n')+'\n';}
function hardExample(){setq(buildHardDemo());}                          // 2D denso 5x5 -> ruta dura, carga siempre
function cliffordBig(){var n=64,L=['OPENQASM 2.0;','include "qelib1.inc";','qreg q['+n+'];'];var G=['h','s','x','z'];for(var d=0;d<8;d++){for(var i=0;i<n;i++)L.push(G[(i*7+d*3)%4]+' q['+i+'];');for(var i=d%2;i<n-1;i+=2)L.push((((i+d)%2)?'cz':'cx')+' q['+i+'],q['+(i+1)+'];');}setq(L.join('\n')+'\n');}  // n=64 Clifford -> #T=0 -> Stim exacto: muestra escala + el '+' (▶ Computar resultado)
function deep1D(){var n=24,L=['OPENQASM 2.0;','include "qelib1.inc";','qreg q['+n+'];'];for(var i=0;i<n;i++)L.push('h q['+i+'];');for(var d=0;d<20;d++){for(var i=d%2;i<n-1;i+=2)L.push('cx q['+i+'],q['+(i+1)+'];');for(var i=0;i<n;i++)L.push((((i*5+d)%4)===0?'t':'h')+' q['+i+'];');}setq(L.join('\n')+'\n');}  // n=24 1D profundo -> MPS/tensor
function genFromPanel(){genAt(dials.Magic,dials.Spread,dials.Book)}
window.onload=()=>{$('qasm').value=DEMO;onInput();if(location.hash==='#3d'){clearTimeout(window._t);resetDiagnostics();}applyLang();renderHistory();buildDecisionPanel();if(location.hash==='#3d')setTimeout(function(){mode('gen');phaseMode('3d');},80)}
// ===== DECISION PANEL: Big 3 + Scientist + CFO View =====
// Pricing publicado (espejo EXACTO de economics.py). El tiempo clasico sigue MEDIDO (server); aqui solo
// recalculamos las cifras al cambiar SUPUESTOS DECLARADOS (vendor / precision / tamano de campana).
var PRICING={'IonQ Forte (AWS Braket)':{shot:0.08,task:0.30,shot_us:200},'IonQ Aria (AWS Braket) [LEGACY]':{shot:0.03,task:0.30,shot_us:200},
  'Rigetti (AWS Braket)':{shot:0.00035,task:0.30,shot_us:1},
  'IBM (pay-as-you-go)':{shot:0,task:0,per_second:1.60,shot_us:1}};
var QUEUE_S=60,CPU_RATE_HR=0.10;
var ASSUMP={vendor:'IonQ Forte (AWS Braket)',eps:0.01,campaign:1000};
function recomputeEcon(base,a){
  if(!base)return base;var p=PRICING[a.vendor]||PRICING['IonQ Forte (AWS Braket)'];
  var mitig=base.mitig||1,tf=base.t_factor||1;        // factores del CIRCUITO (mitigacion error, tiempo/shot)
  var shots=Math.round(1/(a.eps*a.eps)),shots_eff=Math.round(shots*mitig);
  var qpu=+(p.task+shots_eff*p.shot+(p.per_second||0)*shots_eff*(p.shot_us||1)*tf*1e-6).toFixed(2);
  var t_qpu=shots_eff*(p.shot_us||100)*tf*1e-6+QUEUE_S;
  var o=Object.assign({},base,{shots:shots,shots_eff:shots_eff,eps:a.eps,vendor:a.vendor,campaign:a.campaign,qpu_cost_eval:qpu,t_qpu_s:+t_qpu.toFixed(1)});
  if(base.classical_sim_s!=null){var cls=base.classical_cost_eval||0;   // clasico MEDIDO, no se toca
    o.savings_eval=+(qpu-cls).toFixed(2);o.savings_campaign=Math.round((qpu-cls)*a.campaign);
    var triv=base.classical_sim_s<1e-3;o.trivial=triv;   // VULN-2: sin speedup enganoso en circuitos triviales
    o.speedup=triv?null:Math.round(t_qpu/base.classical_sim_s);}
  return o;
}
function econControlsHTML(){
  var vops=Object.keys(PRICING).map(function(v){return'<option'+(v===ASSUMP.vendor?' selected':'')+'>'+v+'</option>';}).join('');
  var eops=[['0.1','1e-1 (100 shots)'],['0.03','3e-2 (~1k shots)'],['0.01','1e-2 (10k shots)'],['0.003','3e-3 (~100k shots)']]
    .map(function(e){return'<option value="'+e[0]+'"'+(+e[0]===ASSUMP.eps?' selected':'')+'>'+e[1]+'</option>';}).join('');
  var EN=LANG==='en';
  return'<div class="dp-assump"><div class="dp-assump-t">'+(EN?'Assumptions (editable · classical cost stays MEASURED):':'Supuestos (editables · el coste clasico sigue MEDIDO):')+'</div>'+
    '<div class="dp-assump-row"><label>Vendor</label><select id="as-vendor">'+vops+'</select></div>'+
    '<div class="dp-assump-row"><label>'+(EN?'Precision':'Precision')+' &epsilon;</label><select id="as-eps">'+eops+'</select></div>'+
    '<div class="dp-assump-row"><label for="as-camp">'+(EN?'Campaign (#evals)':'Campana (#evals)')+'</label><input id="as-camp" type="number" min="1" value="'+ASSUMP.campaign+'" aria-label="'+(EN?'campaign size (number of evaluations)':'tamano de campana (numero de evaluaciones)')+'"></div></div>';
}
// DESGLOSE economico itemizado (cada linea con su PROCEDENCIA). Responde a 'el caso de negocio no se desglosa'.
function econBreakdownHTML(e,isTractable,material){
  if(!e)return'';var EN=LANG==='en';
  var TAG={MED:[EN?'measured':'medido','#10b981'],PUB:[EN?'published':'publicado','#60a5fa'],
    DER:[EN?'derived':'derivado','#a78bfa'],EST:[EN?'estimate':'estimacion','#f59e0b']};
  var rows;
  if(isTractable&&e.classical_sim_s!=null){
    rows=[[EN?'Classical sim':'Sim clasica',(e.classical_sim_s*1000).toFixed(1)+' ms','$'+(e.classical_cost_eval||0).toFixed(6)+'/eval','MED'],
      ['QPU',(e.shots_eff||e.shots)+' shots ('+(e.two_q_gates||0)+'×2q→×'+(e.mitig||1)+' mitig)',material?'$'+e.qpu_cost_eval+'/eval':(EN?'not material':'no material'),'PUB']];
    if(material)rows=rows.concat([[EN?'Savings / eval':'Ahorro / eval','QPU − '+(EN?'classical':'clasico'),'$'+e.savings_eval,'DER'],
      [EN?'Campaign':'Campana','× '+e.campaign+' evals','$'+(e.savings_campaign||0).toLocaleString(),'DER'],
      [EN?'Speedup':'Aceleracion','t_QPU / t_cls',(e.trivial||e.speedup==null)?(EN?'trivial':'trivial'):('×'+(e.speedup||0).toLocaleString()),'DER']]);
    else rows.push([EN?'Decision':'Decision',EN?'below economic triage threshold':'bajo umbral de triage economico',EN?'use classical route':'usar ruta clasica','DER']);
  }else{
    rows=[[EN?'Exact sim (HPC)':'Sim exacta (HPC)','~2^'+e.hpc_flops_log2+' FLOPs','$'+e.hpc_cost_eval+'/eval','EST'],
      ['QPU',e.shots+' shots','$'+e.qpu_cost_eval+'/eval','PUB']];
  }
  return'<div class="dp-bd"><div class="dp-bd-h">'+(EN?'Itemized breakdown':'Desglose itemizado')+'</div>'+
    rows.map(function(r){var t=TAG[r[3]];return'<div class="dp-bd-row"><span class="dp-bd-k">'+r[0]+'</span>'+
      '<span class="dp-bd-f">'+r[1]+'</span><span class="dp-bd-v">'+r[2]+'</span>'+
      '<span class="dp-bd-t" style="color:'+t[1]+'">'+t[0]+'</span></div>';}).join('')+
    (e.src?'<div style="font-size:9px;color:#64748b;padding:4px 10px">'+(EN?'source: ':'fuente: ')+e.src+'</div>':'')+'</div>';
}
function econTriageMaterial(s){
  if(!s||!s.econ)return false;
  return s.nqubits>=16||s.tw>=18||s.mps>=8||s.spread>=8||/PROVISIONAL|INTRACTABLE|WALL|nucleo/i.test(s.verdictText||'');
}
function routeComparisonHTML(s){
  var EN=LANG==='en',e=s.econ||{},cpu=s.econ&&s.econ.classical_sim_s!=null?((s.econ.classical_sim_s*1000).toFixed(1)+' ms'):(EN?'measured if tractable':'medido si es tratable');
  var rows=[
    ['CPU local / cloud',cpu,s.tw<18?(EN?'baseline route':'ruta base'):(EN?'pre-check only':'solo pre-check')],
    ['MPS / tensor network','2^'+s.mps,s.mps<=10?(EN?'recommended':'recomendado'):(EN?'stress route':'ruta tensionada')],
    ['Tensor contraction / HPC','treewidth 2^'+s.tw,s.tw>=18?(EN?'evaluate':'evaluar'):(EN?'not needed':'no necesario')],
    ['QPU hardware',(e.shots_eff||e.shots||10000)+' shots',econTriageMaterial(s)?(EN?'candidate only after HPC/noise review':'candidato solo tras revisar HPC/ruido'):(EN?'not a material comparison':'comparacion no material')]
  ];
  return '<div class="dp-bd"><div class=dp-bd-h>'+(EN?'Compute-route comparison':'Comparacion de rutas de computo')+'</div>'+
    rows.map(function(r){return'<div class=dp-bd-row><span class=dp-bd-k>'+r[0]+'</span><span class=dp-bd-f>'+r[1]+'</span><span class=dp-bd-v>'+r[2]+'</span><span class=dp-bd-t style="color:#94a3b8">triage</span></div>';}).join('')+'</div>';
}
// LIMITACIONES / DEUDAS conocidas -- bilingue. Responde a 'las deudas no las veo en ingles'.
function limitationsHTML(){
  var EN=LANG==='en';
  var items=EN?[
    'Scalability: cheap order-parameters scale to n<=60 (fast path). Exact metrics for deep 50-127q circuits remain expensive on a laptop. On the correct declared hardware path (GPU/HPC/QPU validation), this limitation can be broken only if benchmarked wall-time and memory prove it.',
'Input / export: OpenQASM 2.0/3.0 + native Qiskit/Cirq (active) + pytket/Braket importers (code-ready, optional dep) + auto-normalization of pasted QASM via Qiskit. QIR export is active via /api/qir (LLVM IR base profile) WITH round-trip validation (structural + exact-unitary semantic equivalence for n≤7); QIR import remains future work.',
'Noise: range [noisy, coherent] + crossover p* (live slider). The FIDELITY F=1/d+(1-1/d)(1-p)^G is the closed form of the global depolarizing channel — EXACT vs density-matrix sim (|Δ|~1e-15, any n). BUT p* and the noisy diagnostic index do NOT inherit that: they pass through φ=min(1,1/λ), which is HEURISTIC. So F is exact, p* and the noisy phase diagram are order-of-magnitude. Further gap: global-vs-LOCAL 2q depolarizing.',
    'Fast path (n>14): magic (#T) is still exact; only fold(magic)-cost and spread skip the exponential arsenal (kept fast: <~25ms), so the spread↔Stim cross-check is n/a there — verdict from MPS/treewidth (conservative).',
    'Economic case: classical time is MEASURED; QPU cost is PUBLISHED pricing under DECLARED assumptions. QPU spend/speedup is only treated as material above the triage threshold (n / MPS / spread / treewidth); small circuits are not advertised as savings.',
    'Frontend: zero JS frameworks, but the UI loads web fonts (IBM Plex Sans / JetBrains Mono) from the Google Fonts CDN. Offline / air-gapped it degrades to system fonts (no functional break), but it is not strictly dependency-free.'
  ]:[
    'Escalabilidad: los parametros de orden baratos escalan a n<=60 (fast path). Las metricas exactas de circuitos profundos de 50-127q siguen caras en laptop. Sobre el hardware correcto declarado (GPU/HPC/QPU), esta limitacion solo se rompe si el benchmark de tiempo real y memoria lo prueba.',
'Entrada / export: OpenQASM 2.0/3.0 + Qiskit/Cirq nativos (activos) + importadores pytket/Braket (codigo listo, dep opcional) + auto-normalizacion del QASM pegado via Qiskit. Export QIR ya esta activo via /api/qir (LLVM IR base profile) CON validacion round-trip (equivalencia estructural + unitaria exacta para n<=7); import QIR queda como trabajo futuro.',
'Ruido: rango [ruidoso, coherente] + cruce p* (slider en vivo). La FIDELIDAD F=1/d+(1-1/d)(1-p)^G es la forma cerrada del canal depolarizante global — EXACTA vs sim por densidad (|Δ|~1e-15, a cualquier n). PERO p* y la dureza ruidosa NO heredan eso: pasan por φ=min(1,1/λ), que es HEURISTICO. Asi que F es exacta, p* y el diagrama de fases ruidoso son orden de magnitud. Brecha adicional: depolarizante global-vs-LOCAL de 2q.',
    'Fast path (n>14): la magia (#T) sigue siendo exacta; solo el coste fold(magic) y el spread saltan el arsenal exponencial (rapido: <~25ms), asi que el cruce spread↔Stim queda n/a ahi — veredicto por MPS/treewidth (conservador).',
    'Caso economico: el tiempo clasico es MEDIDO; el coste QPU es pricing PUBLICADO bajo supuestos DECLARADOS. El gasto/speedup QPU solo se trata como material sobre el umbral de triage (n / MPS / spread / treewidth); circuitos pequenos no se venden como ahorro.',
    'Frontend: cero frameworks JS, pero la UI carga fuentes web (IBM Plex Sans / JetBrains Mono) del CDN de Google Fonts. Offline / air-gapped degrada a fuentes del sistema (no rompe), pero no es estrictamente sin-dependencias.'
  ];
  return'<ul class="dp-lim">'+items.map(function(x){return'<li>'+x+'</li>';}).join('')+'</ul>';
}
function limitationPlanHTML(){
  var EN=LANG==='en';
  var rows=EN?[
    ['Hardware proof path','GPU/HPC/QPU benchmark','Run the same benchmark corpus on declared hardware tiers. If wall-time and memory break the laptop ceiling, mark limitation #1 as hardware-resolved for that tier, not globally solved.','artifact: benchmark_results_hardware.csv + raw logs'],
    ['QIR path','QIR export now; import next','Keep QIR export as an execution handoff today. Add QIR import/round-trip tests so Atlas can diagnose compiler outputs directly, not only OpenQASM inputs.','artifact: circuit.ll + qir_roundtrip_report.md'],
    ['Noise model upgrade','local 2q channel','Replace the global depolarizing shortcut for p* with local two-qubit channel validation on small n and fit an error envelope for larger n.','artifact: noise_local_validation.csv'],
    ['Score calibration','larger public corpus','Expand beyond 27 circuits and calibrate route confidence against expected-route labels and measured simulator failures.','artifact: validation_stats.json with confidence calibration']
  ]:[
    ['Ruta de prueba en hardware','benchmark GPU/HPC/QPU','Correr el mismo corpus en tiers de hardware declarados. Si tiempo real y memoria rompen el techo de laptop, marcar la limitacion #1 como resuelta para ese tier, no como solucion universal.','artefacto: benchmark_results_hardware.csv + logs crudos'],
    ['Ruta QIR','export QIR ahora; import despues','Mantener export QIR como handoff de ejecucion hoy. Agregar import/round-trip QIR para que Atlas diagnostique salidas de compilador, no solo entradas OpenQASM.','artefacto: circuit.ll + qir_roundtrip_report.md'],
    ['Mejora de ruido','canal local 2q','Reemplazar el atajo depolarizante global para p* con validacion de canal local de dos qubits en n pequeno y ajustar una envolvente de error para n grande.','artefacto: noise_local_validation.csv'],
    ['Calibracion del score','corpus publico mayor','Expandir mas alla de 27 circuitos y calibrar confianza de ruta contra etiquetas expected-route y fallos medidos de simuladores.','artefacto: validation_stats.json con calibracion']
  ];
  return '<div class=dp-plan>'+rows.map(function(r){return '<div class=dp-plan-row><div class=dp-plan-h><span>'+r[0]+'</span><span class=dp-plan-tag>'+r[1]+'</span></div><div class=dp-plan-d>'+r[2]+'</div><div class=dp-plan-proof>'+r[3]+'</div></div>';}).join('')+'</div>';
}
function wireEconControls(){
  var v=document.getElementById('as-vendor'),e=document.getElementById('as-eps'),c=document.getElementById('as-camp');
  function upd(){if(v)ASSUMP.vendor=v.value;if(e)ASSUMP.eps=+e.value;if(c)ASSUMP.campaign=Math.max(1,+c.value||1);
    if(window.lastAtlas&&window.lastAtlas._econBase)window.lastAtlas.econ=recomputeEcon(window.lastAtlas._econBase,ASSUMP);
    buildDecisionPanel();document.getElementById('decision-panel').classList.add('open');}
  if(v)v.addEventListener('change',upd);if(e)e.addEventListener('change',upd);if(c)c.addEventListener('change',upd);
}
// Despachador de las acciones de 'Proximos pasos' (antes eran decorativas: onclick=null)
function decisionAction(act){
  if(/Stim/i.test(act)){otab('Log');analyze();}                       // re-analiza y abre el Log (validacion Stim)
  else if(/variant|complex|complej|Genera/i.test(act)){               // genera variante DURA (rejilla 2D)
    dials.Tw='high';genAt('high','high','core');document.getElementById('decision-panel').classList.remove('open');}
  else if(/QIR/i.test(act)){exportQIR();}                             // handoff LLVM IR / QIR
  else if(/Export|QASM/i.test(act)){                                  // descarga el QASM actual
    var q=$('qasm').value||'';var blob=new Blob([q],{type:'text/plain'});var u=URL.createObjectURL(blob);
    var a=document.createElement('a');a.href=u;a.download='circuit_atlas_'+Date.now()+'.qasm';a.click();URL.revokeObjectURL(u);}
  else if(/HPC/i.test(act)){otab('Log');$('st').innerHTML='<span class=g>&#9679; '+(LANG==='en'?'See Log: treewidth (HPC bound)':'Ver Log: treewidth (cota HPC)')+'</span>';}
  else if(/QPU/i.test(act)){otab('Resultado');}
  else if(/Mitig/i.test(act)){otab('Log');}
}
// ===== CONSTRUCTOR VISUAL (click-para-colocar -> genera QASM -> analiza; one-way, sin divergencia de sync)
// ===== CONSTRUCTOR LAB (IBM-tier): columnas de tiempo, paleta categorizada, drag-drop, metricas/QASM live
var builderN=4,builderItems=[],builderSel='h',builderPend=[],builderHist=[];
var B_GATE={h:{l:'H',c:'#1d4ed8'},x:{l:'X',c:'#1d4ed8'},y:{l:'Y',c:'#1d4ed8'},z:{l:'Z',c:'#1d4ed8'},s:{l:'S',c:'#1d4ed8'},sdg:{l:'S†',c:'#1d4ed8'},cx:{l:'CX',c:'#1d4ed8'},cz:{l:'CZ',c:'#1d4ed8'},t:{l:'T',c:'#7c3aed'},tdg:{l:'T†',c:'#7c3aed'},ccx:{l:'CCX',c:'#7c3aed'},rx:{l:'Rx',c:'#0f766e'},ry:{l:'Ry',c:'#0f766e'},rz:{l:'Rz',c:'#0f766e'}};
function B_CATS(){var EN=LANG==='en';return[
  {n:'Clifford',hint:EN?'efficiently simulable (Stim, any n)':'simulable eficientemente (Stim, cualquier n)',g:['h','x','y','z','s','sdg','cx','cz']},
  {n:EN?'Magic':'Magia',hint:EN?'adds #T, raises non-Clifford diagnostic signal':'anade #T, incrementa la senal diagnostica no-Clifford',g:['t','tdg','ccx']},
  {n:EN?'Rotations':'Rotaciones',hint:EN?'parametric (pi/4), heuristic if not pi/2^k':'parametricas (pi/4), heuristico si no son pi/2^k',g:['rx','ry','rz']}];}
function bArity(op){return op==='ccx'?3:(op==='cx'||op==='cz')?2:1;}
function bIsRot(op){return op==='rx'||op==='ry'||op==='rz';}
function bCloneItems(items){return JSON.parse(JSON.stringify(items||[]));}
function bSnap(){builderHist.push({n:builderN,items:bCloneItems(builderItems)});if(builderHist.length>80)builderHist.shift();}
function bSameGate(a,op,qs){return a&&a.op===op&&a.qs.length===qs.length&&a.qs.every(function(q,i){return q===qs[i];});}
function bThetaExpr(){var el=document.getElementById('builder-theta');return (el&&el.value.trim())||'pi/4';}
function bRenderPalette(){var p=document.getElementById('builder-pal');if(!p)return;
  p.innerHTML=B_CATS().map(function(cat){return'<div class=bcat><div class=bcat-h>'+cat.n+'</div><div class=bcat-g>'+
    cat.g.map(function(op){var G=B_GATE[op];return'<button class="bgate'+(op===builderSel?' sel':'')+'" data-g="'+op+'" draggable=true ondragstart="builderDragStart(event,\''+op+'\')" onclick="bSel(\''+op+'\')" style="background:'+G.c+'" title="'+G.l+' · '+cat.n+'" aria-label="Compuerta '+G.l+'">'+G.l+'</button>';}).join('')+
    '</div><div class=bcat-hint>↳ '+cat.hint+'</div></div>';}).join('');}
function openBuilder(){document.getElementById('builder-modal').classList.add('open');document.body.classList.add('modal-open');bRenderPalette();builderRender();bStatus();}
function closeBuilder(){document.getElementById('builder-modal').classList.remove('open');document.body.classList.remove('modal-open');}
function bSel(g){builderSel=g;builderPend=[];document.querySelectorAll('.bgate').forEach(function(b){b.classList.toggle('sel',b.getAttribute('data-g')===g);});bStatus();}
function bMaxCol(){var m=-1;builderItems.forEach(function(it){if(it.col>m)m=it.col;});return m;}
function bAt(q,c){for(var i=0;i<builderItems.length;i++){if(builderItems[i].col===c&&builderItems[i].qs.indexOf(q)>=0)return builderItems[i];}return null;}
function bPlace(q,c){var ex=bAt(q,c);
  var ar=bArity(builderSel);
  if(ar===1){var next={op:builderSel,qs:[q],col:c};if(bIsRot(builderSel))next.theta=bThetaExpr();
    if(bSameGate(ex,builderSel,[q])){bSnap();builderItems=builderItems.filter(function(it){return it!==ex;});}
    else{bSnap();builderItems=builderItems.filter(function(it){return it!==ex;});builderItems.push(next);}
    builderPend=[];}
  else{if(builderPend.length&&builderPend[0].c!==c)builderPend=[];                 // distinta columna -> reinicia
    if(!builderPend.some(function(p){return p.q===q;}))builderPend.push({q:q,c:c});
    if(builderPend.length===ar){var qs=builderPend.map(function(p){return p.q;}),conf=[];
      qs.forEach(function(qq){var hit=bAt(qq,c);if(hit&&conf.indexOf(hit)<0)conf.push(hit);});
      if(conf.length===1&&bSameGate(conf[0],builderSel,qs)){bSnap();builderItems=builderItems.filter(function(it){return it!==conf[0];});}
      else{bSnap();builderItems=builderItems.filter(function(it){return conf.indexOf(it)<0;});builderItems.push({op:builderSel,qs:qs,col:c});}
      builderPend=[];}}
  builderRender();bStatus();}
function bCell(q,c){bPlace(q,c);}
function bCellKey(e,q,c){var k=e.key;
  if(k==='Enter'||k===' '){e.preventDefault();bCell(q,c);return;}
  var dq=0,dc=0;
  if(k==='ArrowUp')dq=-1;else if(k==='ArrowDown')dq=1;else if(k==='ArrowLeft')dc=-1;else if(k==='ArrowRight')dc=1;else return;
  e.preventDefault();
  var nq=Math.max(0,Math.min(builderN-1,q+dq)),nc=Math.max(0,Math.min(_bNcol-1,c+dc));
  var el=document.getElementById('bcell-'+nq+'-'+nc);if(el)el.focus();}
async function bMeasure(){var out=document.getElementById('builder-measure');if(!out)return;var EN=LANG==='en';
  if(!builderItems.length){out.innerHTML='<span style="color:#64748b">'+(EN?'place gates first':'pon compuertas primero')+'</span>';return;}
  out.innerHTML='<span style="color:#94a3b8">'+(EN?'measuring spread / MPS / treewidth ...':'midiendo spread / MPS / treewidth ...')+'</span>';
  try{var o=await post('/api/diagnose',{qasm:builderQASM()});
    var c=o.costs_log2||{},ra=o.route_adjudication||{},V=(o.ground_truth&&o.ground_truth.validations)||{};
    var sp=c['spread(local)'],mps=c['MPS(entangle)'],tw=c['contraction(treewidth)'],trunc=V.mps_truncated;
    var mpsL=(mps==null)?'n/a':(trunc?'&ge;2^'+mps+' '+(EN?'(truncated lower bound)':'(cota inferior truncada)'):'2^'+mps);
    var spL=(sp==null)?(EN?'n/a (n&gt;14)':'n/a (n&gt;14)'):'2^'+sp;
    var route=(ra.route||'n/a'),conf=(ra.confidence&&ra.confidence.score!=null)?ra.confidence.score:'n/a';
    out.innerHTML='<b>'+(EN?'Measured':'Medido')+':</b> #T '+(o.t_count||0)+' · spread '+spL+' · MPS '+mpsL+
      ' · treewidth 2^'+(tw==null?'n/a':tw)+' · '+(EN?'route':'ruta')+' <b style="color:#38bdf8">'+route+
      '</b> ('+(EN?'confidence':'confianza')+' '+conf+')';
  }catch(err){out.innerHTML='<span style="color:#f87171">'+(EN?'measure failed':'fallo la medicion')+'</span>';}}
function builderDragStart(e,op){bSel(op);try{e.dataTransfer.setData('text/plain',op);}catch(_){}}
function builderDragOver(e){e.preventDefault();}
function builderDrop(e,q,c){e.preventDefault();bPlace(q,c);}
var _ghostQC=[-1,-1];function bGhost(q,c){_ghostQC=[q,c];var g=document.getElementById('bghost');if(!g)return;
  var hot=document.querySelector('#builder-circ .bg-rect.hot');if(hot)hot.classList.remove('hot');           // limpia resaltado previo
  var here=document.querySelector('#builder-circ .bg-rect[data-qc="'+q+'-'+c+'"]');if(here)here.classList.add('hot');  // resalta gate bajo el cursor
  if(q<0||bArity(builderSel)!==1||bAt(q,c)){g.innerHTML='';return;}
  var CW=46,RH=42,x0=54,y0=30,cx=x0+c*CW+CW/2,cy=y0+q*RH+RH/2,G=B_GATE[builderSel];
  g.innerHTML='<rect x="'+(cx-15)+'" y="'+(cy-15)+'" width="30" height="30" rx="6" fill="'+G.c+'" opacity="0.35"/><text x="'+cx+'" y="'+(cy+4)+'" fill="#fff" font-size="11" font-weight="700" text-anchor="middle" opacity="0.6">'+G.l+'</text>';}
function bStatus(){var s=document.getElementById('builder-status');if(!s)return;var EN=LANG==='en',ar=bArity(builderSel),G=B_GATE[builderSel];
  if(ar===1)s.textContent=(EN?'click a cell to place ':'clic en una celda para poner ')+G.l+(bIsRot(builderSel)?'('+bThetaExpr()+')':'');
  else{var left=ar-builderPend.length;s.textContent=(EN?'click '+left+' qubit(s) in the same column for ':'clic en '+left+' qubit(s) de la misma columna para ')+G.l;}}
function bUndo(){var h=builderHist.pop();if(!h)return;builderN=h.n;builderItems=bCloneItems(h.items);builderPend=[];
  var nv=document.getElementById('bm-nval'),sl=document.getElementById('builder-n');if(nv)nv.textContent=builderN;if(sl)sl.value=builderN;builderRender();bStatus();}
function bClear(){if(!builderItems.length&&!builderPend.length)return;bSnap();builderItems=[];builderPend=[];builderRender();bStatus();}
function bSetN(v){var nextN=Math.max(1,Math.min(16,+v||4)),nextItems=builderItems.filter(function(it){return it.qs.every(function(q){return q<nextN;});});
  if(nextN!==builderN||nextItems.length!==builderItems.length)bSnap();builderN=nextN;var nv=document.getElementById('bm-nval');if(nv)nv.textContent=builderN;
  builderItems=nextItems;builderRender();bStatus();}
function _cellXY(q,c){return[54+c*46+23,30+q*42+21];}
var _bNcol=5;
function builderRender(){var pane=document.getElementById('builder-circ');if(!pane)return;
  var n=builderN,ncol=Math.max(bMaxCol()+2,5),CW=46,RH=42,x0=54,y0=30,W=x0+ncol*CW+30,H=y0+n*RH+14;
  _bNcol=ncol;var _bm=document.getElementById('builder-measure');if(_bm)_bm.innerHTML='';  // medicion previa queda obsoleta al mutar
  var s='<svg viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'">';
  for(var c=0;c<ncol;c++)s+='<text x="'+(x0+c*CW+CW/2)+'" y="16" fill="#475569" font-size="9" text-anchor="middle">t='+c+'</text>';
  for(var q=0;q<n;q++){var y=y0+q*RH+RH/2;
    s+='<text x="8" y="'+(y+4)+'" fill="#94a3b8" font-family="monospace" font-size="11">q['+q+']</text>';
    s+='<line x1="'+x0+'" y1="'+y+'" x2="'+(x0+ncol*CW)+'" y2="'+y+'" stroke="#2a2a3e" stroke-width="1.5"/>';
    s+='<circle cx="'+(x0+ncol*CW+12)+'" cy="'+y+'" r="6" fill="none" stroke="#475569" stroke-width="1.5"/><circle cx="'+(x0+ncol*CW+12)+'" cy="'+(y-1)+'" r="3" fill="none" stroke="#475569" stroke-width="1"/>';}
  builderItems.forEach(function(it){var G=B_GATE[it.op],ys=it.qs.map(function(q){return y0+q*RH+RH/2;}),cx=x0+it.col*CW+CW/2,lab=G.l+(it.theta?'('+it.theta+')':'');
    if(it.qs.length>=2){s+='<line x1="'+cx+'" y1="'+Math.min.apply(null,ys)+'" x2="'+cx+'" y2="'+Math.max.apply(null,ys)+'" stroke="#cbd5e1" stroke-width="1.6"/>';
      for(var k=0;k<it.qs.length-1;k++)s+='<circle cx="'+cx+'" cy="'+ys[k]+'" r="4" fill="#cbd5e1"/>';
      var ty=ys[ys.length-1];
      if(it.op==='cz')s+='<circle cx="'+cx+'" cy="'+ty+'" r="4" fill="#cbd5e1"/>';
      else s+='<circle cx="'+cx+'" cy="'+ty+'" r="10" fill="'+G.c+'" stroke="#cbd5e1" stroke-width="1.5"/><line x1="'+(cx-10)+'" y1="'+ty+'" x2="'+(cx+10)+'" y2="'+ty+'" stroke="#fff" stroke-width="1.5"/><line x1="'+cx+'" y1="'+(ty-10)+'" x2="'+cx+'" y2="'+(ty+10)+'" stroke="#fff" stroke-width="1.5"/>';
    }else{var y=ys[0];s+='<rect class="bg-rect" data-qc="'+it.qs[0]+'-'+it.col+'" x="'+(cx-15)+'" y="'+(y-15)+'" width="30" height="30" rx="6" fill="'+G.c+'" filter="url(#bsh)"/><text x="'+cx+'" y="'+(y+4)+'" fill="#fff" font-size="11" font-weight="700" text-anchor="middle" pointer-events="none"><title>'+lab+'</title>'+G.l+'</text>';}});
  for(var q=0;q<n;q++)for(var c=0;c<ncol;c++){var X=x0+c*CW,Y=y0+q*RH;
    s+='<rect class="bg-cell" id="bcell-'+q+'-'+c+'" tabindex="0" role="button" aria-label="qubit '+q+', columna '+c+'" x="'+X+'" y="'+Y+'" width="'+CW+'" height="'+RH+'" fill="transparent" style="cursor:pointer" onclick="bCell('+q+','+c+')" onkeydown="bCellKey(event,'+q+','+c+')" ondragover="builderDragOver(event)" ondrop="builderDrop(event,'+q+','+c+')" onmouseover="bGhost('+q+','+c+')" onmouseout="bGhost(-1,-1)"></rect>';}
  s+='<defs><filter id=bsh x=-30% y=-30% width=160% height=160%><feDropShadow dx=0 dy=2 stdDeviation=1.5 flood-color=#000 flood-opacity=0.4/></filter></defs><g id="bghost"></g></svg>';
  pane.innerHTML=s;updateBuilderMetrics();updateBuilderQasmPreview();if(bStateOn)bRenderState();}
// ===== SIMULADOR de STATEVECTOR (composer): aplica las compuertas a un vector complejo 2^n =====
var bStateOn=false;
function _popcount(x){var c=0;while(x){c+=x&1;x>>>=1;}return c;}
function _thetaVal(expr){expr=(expr||'pi/4').toLowerCase().replace(/\s+/g,'').replace(/π/g,'pi');
  var m=expr.match(/^pi(?:\/(\d+(?:\.\d+)?))?$/);if(m)return Math.PI/(m[1]?+m[1]:1);
  m=expr.match(/^(-?\d+(?:\.\d+)?)\*?pi(?:\/(\d+(?:\.\d+)?))?$/);if(m)return (+m[1])*Math.PI/(m[2]?+m[2]:1);
  var v=parseFloat(expr);return isFinite(v)?v:Math.PI/4;}
function _gmat(op,theta){var SQ=Math.SQRT1_2,a=Math.cos(Math.PI/4),b=Math.sin(Math.PI/4),th=_thetaVal(theta),cc=Math.cos(th/2),ss=Math.sin(th/2);
  switch(op){                                           // [m00r,m00i, m01r,m01i, m10r,m10i, m11r,m11i]
    case 'h':return [SQ,0, SQ,0, SQ,0, -SQ,0];
    case 'x':return [0,0, 1,0, 1,0, 0,0];
    case 'y':return [0,0, 0,-1, 0,1, 0,0];
    case 'z':return [1,0, 0,0, 0,0, -1,0];
    case 's':return [1,0, 0,0, 0,0, 0,1];
    case 'sdg':return [1,0, 0,0, 0,0, 0,-1];
    case 't':return [1,0, 0,0, 0,0, a,b];
    case 'tdg':return [1,0, 0,0, 0,0, a,-b];
    case 'rx':return [cc,0, 0,-ss, 0,-ss, cc,0];
    case 'ry':return [cc,0, -ss,0, ss,0, cc,0];
    case 'rz':return [Math.cos(-th/2),Math.sin(-th/2), 0,0, 0,0, Math.cos(th/2),Math.sin(th/2)];
    default:return [1,0,0,0,0,0,1,0];
  }}
function _applyMat(re,im,n,t,m,ctrls){var N=1<<n,tb=1<<t;
  for(var i=0;i<N;i++){if(i&tb)continue;var ok=true;for(var k=0;k<ctrls.length;k++){if(!(i&(1<<ctrls[k]))){ok=false;break;}}if(!ok)continue;
    var j=i|tb,ar=re[i],ai=im[i],br=re[j],bi=im[j];
    re[i]=m[0]*ar-m[1]*ai+m[2]*br-m[3]*bi; im[i]=m[0]*ai+m[1]*ar+m[2]*bi+m[3]*br;
    re[j]=m[4]*ar-m[5]*ai+m[6]*br-m[7]*bi; im[j]=m[4]*ai+m[5]*ar+m[6]*bi+m[7]*br;}}
function bSim(){var n=builderN;if(n>7||n<1)return null;          // cap: 2^7=128 estados (legible)
  var N=1<<n,re=new Float64Array(N),im=new Float64Array(N);re[0]=1;
  builderItems.slice().sort(function(a,b){return a.col-b.col;}).forEach(function(it){
    var op=it.op,qs=it.qs;
    if(op==='cx')_applyMat(re,im,n,qs[1],_gmat('x'),[qs[0]]);
    else if(op==='cz')_applyMat(re,im,n,qs[1],_gmat('z'),[qs[0]]);
    else if(op==='ccx')_applyMat(re,im,n,qs[2],_gmat('x'),[qs[0],qs[1]]);
    else _applyMat(re,im,n,qs[0],_gmat(op,it.theta),[]);});
  return {re:re,im:im,n:n};}
function bProbsSVG(sim){var n=sim.n,N=1<<n,re=sim.re,im=sim.im,x0=34,y0=14,gw=Math.max(220,N*16),gh=150;
  var W=x0+gw+12,H=y0+gh+(n<=4?40:14);var s='<svg viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'">';
  for(var tk=0;tk<=100;tk+=25){var y=y0+gh-gh*tk/100;s+='<line x1="'+x0+'" y1="'+y+'" x2="'+(x0+gw)+'" y2="'+y+'" stroke="rgba(255,255,255,0.06)"/><text x="'+(x0-5)+'" y="'+(y+3)+'" fill="#64748b" font-size="8" text-anchor="end">'+tk+'</text>';}
  var bw=gw/N;for(var i=0;i<N;i++){var p=re[i]*re[i]+im[i]*im[i],x=x0+i*bw,h=gh*p;
    if(p>1e-6)s+='<rect x="'+(x+bw*0.15).toFixed(1)+'" y="'+(y0+gh-h).toFixed(1)+'" width="'+(bw*0.7).toFixed(1)+'" height="'+h.toFixed(1)+'" fill="#3b82f6" rx="1.5"/>';
    if(n<=4){var lx=x+bw/2;s+='<text x="'+lx.toFixed(1)+'" y="'+(y0+gh+10)+'" fill="#64748b" font-size="7" text-anchor="end" transform="rotate(-55 '+lx.toFixed(1)+','+(y0+gh+10)+')">'+i.toString(2).padStart(n,'0')+'</text>';}}
  s+='</svg>';return '<div class=bstate-card><div class=bstate-h>Probabilities (%)</div>'+s+'</div>';}
function bQsphereSVG(sim){var n=sim.n,N=1<<n,re=sim.re,im=sim.im,R=86,cx=110,cy=104;
  var s='<svg viewBox="0 0 220 210" width="220" height="210">';
  s+='<circle cx="'+cx+'" cy="'+cy+'" r="'+R+'" fill="none" stroke="rgba(255,255,255,0.12)"/>';
  s+='<ellipse cx="'+cx+'" cy="'+cy+'" rx="'+R+'" ry="'+(R*0.30).toFixed(0)+'" fill="none" stroke="rgba(255,255,255,0.07)"/>';
  s+='<line x1="'+cx+'" y1="'+(cy-R)+'" x2="'+cx+'" y2="'+(cy+R)+'" stroke="rgba(255,255,255,0.05)"/>';
  var byW={};for(var i=0;i<N;i++){var w=_popcount(i);(byW[w]=byW[w]||[]).push(i);}
  var nodes='';for(var w=0;w<=n;w++){var ring=byW[w]||[],cnt=ring.length;
    for(var k=0;k<cnt;k++){var idx=ring[k],mag=Math.sqrt(re[idx]*re[idx]+im[idx]*im[idx]);if(mag<0.03)continue;
      var th=Math.PI*w/Math.max(1,n),ph=2*Math.PI*k/cnt;
      var X=Math.sin(th)*Math.cos(ph),Y=Math.cos(th),Z=Math.sin(th)*Math.sin(ph);
      var px=(cx+R*X).toFixed(1),py=(cy-R*(Y*0.92-Z*0.30)).toFixed(1);
      var hue=(((Math.atan2(im[idx],re[idx]))/(2*Math.PI))*360+360)%360,col='hsl('+hue.toFixed(0)+',70%,62%)';
      nodes+='<line x1="'+cx+'" y1="'+cy+'" x2="'+px+'" y2="'+py+'" stroke="'+col+'" stroke-width="1" opacity="0.45"/>';
      nodes+='<circle cx="'+px+'" cy="'+py+'" r="'+(2+5*mag).toFixed(1)+'" fill="'+col+'"><title>|'+idx.toString(2).padStart(n,'0')+'⟩  p='+(mag*mag*100).toFixed(1)+'%</title></circle>';}}
  s+=nodes+'<text x="'+cx+'" y="'+(cy-R-3)+'" fill="#94a3b8" font-size="8" text-anchor="middle">|'+('0'.repeat(n))+'⟩</text></svg>';
  return '<div class=bstate-card><div class=bstate-h>Q-sphere</div>'+s+'</div>';}
function bRenderState(){var el=document.getElementById('builder-state');if(!el)return;var EN=LANG==='en';
  if(!builderItems.length){el.innerHTML='<div class=bstate-empty>'+(EN?'Place gates to see the state.':'Coloca compuertas para ver el estado.')+'</div>';return;}
  var sim=bSim();
  if(!sim){el.innerHTML='<div class=bstate-empty>'+(EN?'State view limited to n≤7 qubits (n='+builderN+').':'Vista de estado limitada a n≤7 qubits (n='+builderN+').')+'</div>';return;}
  el.innerHTML='<div class=bstate-grid>'+bProbsSVG(sim)+bQsphereSVG(sim)+'</div>';}
function bToggleState(){bStateOn=!bStateOn;
  var c=document.getElementById('builder-circ'),st=document.getElementById('builder-state'),b=document.getElementById('bm-stateview');
  if(c)c.style.display=bStateOn?'none':'';if(st)st.style.display=bStateOn?'block':'none';
  if(b)b.classList.toggle('on',bStateOn);if(bStateOn)bRenderState();}
function updateBuilderMetrics(){var m=document.getElementById('builder-metrics');if(!m)return;var EN=LANG==='en';
  var tcount=builderItems.filter(function(it){return it.op==='t'||it.op==='tdg';}).length;
  var n2q=builderItems.filter(function(it){return it.op==='cx'||it.op==='cz';}).length;
  var n3q=builderItems.filter(function(it){return it.op==='ccx';}).length;
  var depth=builderItems.length?bMaxCol()+1:0;
  var nonCliff=builderItems.some(function(it){return it.op==='t'||it.op==='tdg'||it.op==='ccx'||bIsRot(it.op);});
  var libro=nonCliff?'core':'stabilizer';
  var possibleEdges=Math.max(1,builderN*(builderN-1)/2),density=Math.min(1,(n2q+n3q*3)/possibleEdges);
  var col=tcount===0?'#34d399':tcount<=5?'#fbbf24':'#f87171';
  m.innerHTML='<span style="color:'+col+';font-weight:700">#T: '+tcount+'</span> · '+(EN?'structure':'estructura')+': <b>'+libro+'</b> · '+(EN?'interaction density':'densidad de interaccion')+': '+density.toFixed(2)+' · '+(EN?'depth':'profundidad')+': '+depth+' · n_2q: '+n2q+(n3q?' · n_3q: '+n3q+' (~'+(n3q*6)+' CX)':'')+'<br><span style="color:#64748b">'+(EN?'pre-diagnostic inputs only; MPS/treewidth are measured after Use & analyze':'solo inputs pre-diagnostico; MPS/treewidth se miden tras Usar y analizar')+'</span>';}
function updateBuilderQasmPreview(){var p=document.getElementById('builder-qasm-preview');if(p)p.value=builderItems.length?builderQASM():'(vacio)';}
function builderQASM(){var its=builderItems.slice().sort(function(a,b){return a.col-b.col;});
  var L=['OPENQASM 2.0;','include "qelib1.inc";','qreg q['+builderN+'];'];
  its.forEach(function(it){var op=it.op,qs=it.qs;
    if(bIsRot(op))L.push(op+'('+(it.theta||'pi/4')+') q['+qs[0]+'];');
    else if(qs.length===1)L.push(op+' q['+qs[0]+'];');
    else L.push(op+' '+qs.map(function(q){return'q['+q+']';}).join(',')+';');});
  return L.join('\n');}
function bUse(){if(!builderItems.length){closeBuilder();return;}var q=builderQASM();closeBuilder();mode('dx');setq(q);}  // setq analiza
function parseAtlasState(){
  var o=window.lastAtlas;
  if(o&&o.costs_log2){
    var nqEl=document.getElementById('nq'),nm=nqEl?nqEl.textContent.match(/n=(\d+)/):null;
    return {magic:o.t_count||0,libro:structureLabel(o.libro_flattener||'core'),mps:Math.round(o.costs_log2['MPS(entangle)']||0),
      spread:Math.round(o.costs_log2['spread(local)']||0),tw:Math.round(o.costs_log2['contraction(treewidth)']||0),
      nqubits:nm?parseInt(nm[1]):8,verdictText:o.verdict||'',econ:o.econ||null,hasResults:true};
  }
  return {magic:0,libro:'interacting',mps:1,spread:0,tw:8,nqubits:8,verdictText:'',econ:null,hasResults:false};
}
function generateInsights(s){
  var EN=LANG==='en';
  var magic=s.magic,libro=s.libro,mps=s.mps,spread=s.spread,tw=s.tw,n=s.nqubits,verdict=s.verdictText;
  var isTractable=verdict.includes('TRACTABLE')&&!verdict.includes('INTRACTABLE');
  var viaSpread=verdict.includes('spread');var isIntractable=verdict.includes('INTRACTABLE')||verdict.includes('nucleo')||verdict.includes('WALL');
  var magicLevel=magic<4?(EN?'low':'bajo'):magic<12?(EN?'moderate':'moderado'):magic<24?(EN?'high':'alto'):(EN?'extreme':'extremo');
  var magicPct=Math.min(100,Math.round((magic/32)*100));
  var mpsCost=Math.pow(2,mps),mpsGood=mps<=2,spreadCost=Math.pow(2,Math.max(0,spread)),spreadGood=spread<=2;
  var sowhat,sowhatSub;
  if(isIntractable&&magic>=24){sowhat=EN?'This circuit <strong>stresses the available classical diagnostics</strong>. Treat it as an HPC-first / QPU-later candidate, not as certified advantage.':'Este circuito <strong>tensiona los diagnosticos clasicos disponibles</strong>. Tratalo como candidato HPC primero / QPU despues, no como ventaja certificada.';sowhatSub=EN?('High magic ('+magic+' T-gates) and high-complexity entanglement: deserves deeper validation.'):('Magia elevada ('+magic+' compuertas T) y entrelazamiento de alta complejidad: merece validacion mas profunda.');}
  else if(isIntractable){sowhat=EN?'The circuit is <strong>expensive to simulate</strong>, but marginally intractable.':'El circuito es de <strong>simulacion costosa</strong>, pero marginalmente intratable.';sowhatSub=EN?'Evaluate HPC before committing to QPU investment.':'Evaluar HPC antes de comprometer inversion en QPU.';}
  else if(isTractable&&viaSpread){sowhat=EN?'The circuit is <strong>efficiently classically simulable</strong> under the current diagnostics.':'El circuito es <strong>simulable clasicamente</strong> bajo los diagnosticos actuales.';sowhatSub=EN?'Atlas does not identify a reason to spend QPU time on this circuit.':'Atlas no identifica una razon para gastar tiempo QPU en este circuito.';}
  else if(isTractable&&mps<=0){sowhat=EN?'The circuit is <strong>trivially classically simulable</strong> (near-product state, bond 2<sup>0</sup>=1).':'El circuito es <strong>trivialmente simulable</strong> (estado casi-producto, enlace 2<sup>0</sup>=1).';sowhatSub=EN?'Any device simulates it exactly; no tensor tools needed.':'Cualquier dispositivo lo simula exacto; no hacen falta herramientas de tensor.';}
  else if(isTractable){sowhat=EN?('The circuit is <strong>simulable via tensor networks</strong> (bond dimension = 2<sup>'+mps+'</sup>).'):('El circuito es <strong>simulable via tensor networks</strong> (dimension de enlace = 2<sup>'+mps+'</sup>).');sowhatSub=EN?'Requires tensor tools (quimb/ITensor), but stays in the classical domain.':'Requiere herramientas de tensor (quimb/ITensor), pero permanece en el dominio clasico.';}
  else{sowhat=EN?'The circuit sits in an <strong>indeterminate region</strong>: mixed metrics.':'El circuito se ubica en una <strong>region indeterminada</strong>: metricas mixtas.';sowhatSub=EN?'A deeper analysis is recommended.':'Se recomienda un analisis de mayor profundidad.';}
  var decision;if(isIntractable&&magic>=20)decision=EN?'Evaluate HPC first; QPU candidate later':'Evaluar HPC primero; QPU candidato despues';else if(isTractable)decision=EN?'QPU investment not recommended':'No se recomienda inversion en QPU';else decision=EN?'Evaluate HPC first':'Evaluar HPC previamente';
  var money=[];
  var e=s.econ,material=econTriageMaterial(s);
  if(isTractable&&e){
    if(material)money.push({type:'good',icon:'▲',text:(EN?'<strong>Material QPU spend avoided:</strong> $':'<strong>Gasto QPU material evitado:</strong> $')+e.savings_eval+(EN?'/eval &rarr; <strong>$':'/evaluacion &rarr; <strong>$')+(e.savings_campaign||0).toLocaleString()+'</strong> '+(EN?'over a '+e.campaign+'-eval campaign. QPU avoided: ':'en campana de '+e.campaign+' evals. QPU evitado: ')+e.vendor+', '+(e.shots_eff||e.shots)+' shots, eps='+e.eps+'.'});
    else money.push({type:'neutral',icon:'•',text:EN?'<strong>Economic comparison not material:</strong> this is a small/easy circuit; the relevant decision is simply CPU/MPS, not laptop-vs-IonQ savings.':'<strong>Comparacion economica no material:</strong> este circuito es pequeno/facil; la decision relevante es CPU/MPS, no ahorro laptop-vs-IonQ.'});
    if(e.trivial||e.speedup==null){
      money.push({type:'neutral',icon:'•',text:(EN?'<strong>Classically trivial:</strong> sim measured at ':'<strong>Clasicamente trivial:</strong> sim medida en ')+((e.classical_sim_s||0)*1000).toFixed(2)+(EN?' ms (below ~1ms resolution) -> no meaningful speedup to report (it is effectively free).':' ms (bajo la resolucion ~1ms) -> no hay speedup significativo que reportar (es esencialmente gratis).')});
    }else if(material){
      money.push({type:'good',icon:'▲',text:(EN?'<strong>Speedup:</strong> <strong>':'<strong>Aceleracion:</strong> <strong>')+(e.speedup||0).toLocaleString()+'x</strong>. '+(EN?'Classical sim MEASURED at ':'Simulacion clasica MEDIDA en ')+((e.classical_sim_s||0)*1000).toFixed(0)+(EN?' ms vs ~':' ms frente a ~')+e.t_qpu_s+(EN?' s on QPU (shots + queue).':' s en QPU (shots + cola).')});}
    money.push({type:'neutral',icon:'•',text:(EN?'<strong>Measured classical cost:</strong> $':'<strong>Coste clasico medido:</strong> $')+(e.classical_cost_eval||0).toFixed(6)+(EN?'/eval (cloud CPU). QPU ROI: nil for this case.':'/eval (CPU cloud). Retorno sobre inversion en QPU: nulo para este caso.')});
  }else if(e){
    money.push({type:'bad',icon:'▼',text:(EN?'<strong>Exact simulation (HPC):</strong> ~2<sup>':'<strong>Simulacion exacta (HPC):</strong> ~2<sup>')+e.hpc_flops_log2+'</sup> FLOPs &rarr; $'+e.hpc_cost_eval+'/eval ('+e.hpc_time_s+(EN?' s est.).':' s estimados).')});
    money.push({type:'good',icon:'▲',text:(EN?'<strong>QPU/HPC exploration case:</strong> ':'<strong>Caso para explorar QPU/HPC:</strong> ')+e.qpu_advantage+'. QPU estimate is shown only as a candidate path: $'+e.qpu_cost_eval+'/eval ('+(e.shots_eff||e.shots)+' shots @ eps='+e.eps+').'});
    money.push({type:'neutral',icon:'•',text:(EN?'<strong>Risk:</strong> current hardware noise; assess the error-mitigation overhead before committing.':'<strong>Riesgo:</strong> ruido del hardware actual; evaluar el sobrecoste de mitigacion de errores antes de comprometer la inversion.')});
  }else{
    money.push({type:'neutral',icon:'•',text:EN?'Economic case not available for this circuit.':'Caso economico no disponible para este circuito.'});
  }
  money.push({type:'neutral',icon:'i',text:(EN?'<strong>Methodology:</strong> classical cost <strong>MEASURED</strong> (sim time x cloud CPU rate); QPU cost from <strong>published pricing</strong> (AWS Braket / IBM, ~2025), ':'<strong>Metodologia:</strong> coste clasico <strong>MEDIDO</strong> (tiempo de simulacion x tarifa CPU cloud); coste QPU de <strong>pricing publicado</strong> (AWS Braket / IBM, ~2025), ')+(e?(e.shots_eff||e.shots):10000)+(EN?' shots for precision eps=':' shots para precision eps=')+(e?e.eps:0.01)+(EN?'. Metrics cross-checked with Stim (Clifford checks only, not T simulation), quimb (MPS), cotengra (treewidth upper bound).':'. Metricas con cross-check: Stim (solo checks Clifford, no simula T), quimb (MPS), cotengra (cota superior de treewidth).')});
  var sci=[
    {label:EN?'Magic (non-Clifford)':'Magia (no-Clifford)',code:'#T',value:magic,interp:magicLevel+' · '+magicPct+(EN?'% of practical threshold':'% del umbral practico')},
    {label:EN?'Circuit structure class':'Clase estructural del circuito',code:'structure',value:libro,interp:libro==='interacting'?(EN?'Interacting Clifford+T structure':'Estructura Clifford+T interactuante'):libro==='free'?(EN?'Free-fermion (polynomial)':'Free-fermion (polinomial)'):(EN?'Mixed':'Mixto')},
    {label:EN?'Bond dimension (MPS)':'Dimension de enlace (MPS)',code:'2^'+mps,value:mpsCost+(mpsGood?' ✓':' ⚠'),interp:mpsGood?(EN?'Efficient — tensor network applies':'Eficiente — tensor network aplicable'):(EN?'High bond — costly':'Enlace elevado — coste alto')},
    {label:EN?'Operator spread':'Dispersion del operador',code:'2^'+spread,value:spreadCost+(spreadGood?' ✓':' ⚠'),interp:spreadGood?(EN?'Low — localized operator':'Baja — operador localizado'):(EN?'High — global entanglement':'Alta — entrelazamiento global')},
    {label:EN?'Contraction width':'Anchura de contraccion',code:'2^'+tw,value:'2^'+tw,interp:tw<=10?(EN?'Thin graph — exact sim viable':'Grafo delgado — simulacion exacta viable'):tw<=20?(EN?'Moderate — HPC viable':'Moderada — HPC viable'):(EN?'High — exactly intractable':'Alta — intratable de forma exacta')},
    {label:EN?'Qubit count':'Numero de qubits',code:'n',value:n,interp:n<=10?(EN?'Small scale (direct sim)':'Escala reducida (simulacion directa)'):n<=30?(EN?'NISQ scale':'Escala NISQ'):n<=50?(EN?'Supremacy scale':'Escala de supremacia'):(EN?'Fault-tolerant scale':'Escala tolerante a fallos')}
  ];
  var rec;
  if(isTractable)rec={text:(EN?'This circuit <strong>does not justify QPU time under the current diagnostics</strong>. Classical simulation via ':'Este circuito <strong>no justifica tiempo QPU bajo los diagnosticos actuales</strong>. La simulacion clasica via ')+(viaSpread?(EN?'Pauli propagation':'propagacion de Pauli'):(EN?'MPS / tensor networks':'MPS / tensor networks'))+(EN?' appears practical. Recommendation: use it as a classical baseline, export QIR for compiler handoff, or generate a harder variant for study.':' parece practica. Recomendacion: usarlo como baseline clasico, exportar QIR para handoff de compilador, o generar una variante mas dura para estudiar.'),actions:EN?[(magic>0?'Validate Clifford substructure (Stim)':'Simulate in Stim'),'Generate a higher-complexity variant','Export QIR']:[(magic>0?'Validar subestructura Clifford (Stim)':'Simular en Stim'),'Generar variante de mayor complejidad','Exportar QIR']};
  else rec={text:(EN?'Circuit with <strong>strong simulability-warning indicators</strong>, not certified quantum advantage. Prior HPC evaluation recommended (cotengra), then decide whether hardware validation is worth it. Export QIR if the next step is compiler/hardware handoff.':'Circuito con <strong>indicadores fuertes de advertencia de simulabilidad</strong>, no ventaja cuantica certificada. Se recomienda evaluacion HPC previa (cotengra), luego decidir si vale la pena validacion en hardware. Exporta QIR si el siguiente paso es handoff a compilador/hardware.'),actions:EN?['Evaluate on HPC','Export QIR','Review QPU candidate after HPC']:['Evaluar en HPC','Exportar QIR','Revisar candidato QPU tras HPC']};
  return {sowhat:sowhat,sowhatSub:sowhatSub,decision:decision,money:money,sci:sci,rec:rec,isTractable:isTractable,isIntractable:isIntractable,magicPct:magicPct};
}
function buildDecisionPanel(){
  var panel=document.getElementById('decision-panel');if(!panel)return;panel.innerHTML='';
  var s=parseAtlasState();var ins=s.hasResults?generateInsights(s):null;
  var verdictClass=ins?(ins.isTractable?'tractable':ins.isIntractable?'intractable':'warning'):'warning';
  var decisionColor=ins?(ins.isTractable?'#10b981':ins.isIntractable?'#ef4444':'#f59e0b'):'#94a3b8';
  var magLbl=s.magic>32?(s.magic+' (>'+(LANG==='en'?'threshold':'umbral')+' 32)'):(s.magic+'/32');
  var magicBar=ins?'<div class="dp-gauge"><div class="dp-gauge-label"><span>Magia #T</span><span>'+magLbl+'</span></div><div class="dp-gauge-track"><div class="dp-gauge-fill" style="width:'+ins.magicPct+'%;background:'+(ins.magicPct<40?'#10b981':ins.magicPct<70?'#f59e0b':'#ef4444')+'"></div></div></div>':'';
  var moneyHTML=ins?ins.money.map(function(m){return'<div class="dp-money-row '+m.type+'"><div class="dp-money-icon">'+m.icon+'</div><div class="dp-money-text">'+m.text+'</div></div>';}).join(''):'';
  var sciHTML=ins?ins.sci.map(function(r){return'<div class="dp-sci-row"><div class="dp-sci-label"><code>'+r.code+'</code>'+r.label+'</div><div><div class="dp-sci-val">'+r.value+'</div><div class="dp-sci-interp">'+r.interp+'</div></div></div>';}).join(''):'';
  var recActHTML=ins?ins.rec.actions.map(function(a,i){return'<button class="dp-rec-btn '+(i===0?'primary':'secondary')+'" data-act="'+a.replace(/"/g,'')+'">'+a+'</button>';}).join(''):'';
  var assumpHTML=(ins&&s.econ)?econControlsHTML():'';
  var EN=LANG==='en';
  var DL={t:EN?'Quantum compute triage':'Triage de computo cuantico',sub:EN?'Pre-flight · Route selection · Spend control':'Pre-flight · Seleccion de ruta · Control de gasto',
    s1:EN?'Strategic implication':'Implicacion estrategica',s1q:EN?'Does this use case justify quantum computing?':'¿Justifica este caso de uso la computacion cuantica?',
    s2:EN?'Platform recommendation':'Recomendacion de plataforma',vl:EN?'Investment verdict':'Veredicto de inversion',
    s3:EN?'Compute route economics':'Economia de rutas de computo',s4:EN?'Technical basis':'Fundamento tecnico',s5:EN?'Next steps':'Proximos pasos',
    s6:EN?'Limitation burn-down plan':'Plan para reducir limitaciones',rt:EN?'Recommended action':'Accion recomendada',
    cs:EN?'Classical simulation':'Simulacion clasica',hpc:EN?'HPC cluster':'Clúster HPC',te:EN?'Est. time':'Tiempo estimado',
    viable:'✓ Viable',noeff:EN?'✗ Not efficient':'✗ No eficiente',consider:EN?'✓ Consider':'✓ Considerar',notreq:EN?'— Not required':'— No requerido',
    costhi:EN?'⚠ High cost':'⚠ Coste elevado',ok2:'~ Viable',tbd:EN?'TBD':'Por determinar',
    foot:EN?'Atlas · Quantum compute triage':'Atlas · Triage de computo cuantico',empty:EN?'Analyze a circuit first':'Analiza un circuito primero'};
  var bdHTML=(ins&&s.econ)?(routeComparisonHTML(s)+econBreakdownHTML(s.econ,ins.isTractable,econTriageMaterial(s))):'';
  var sec06=ins?('<div class="dp-section"><div class="dp-section-label" style="color:#f87171"><span class="label-icon" style="background:rgba(248,113,113,0.15)">06</span>'+DL.s6+'</div>'+limitationPlanHTML()+'</div>'):'';
  var limFoot=ins?'<div class=lim-foot><details><summary>'+(EN?'Known limitations / assumptions':'Limitaciones / supuestos conocidos')+'</summary>'+limitationsHTML()+'</details></div>':'';
  panel.innerHTML='<div class="dp-header"><div class="dp-header-top"><div class="dp-logo">'+atlasLogoSVG('dp-logo-net')+'<div><div class="dp-title">'+DL.t+'</div><div class="dp-subtitle">'+DL.sub+'</div></div></div><button class="dp-close" id="dp-close-btn">✕</button></div></div><div class="dp-body">'+(ins?'<nav class="dp-index" aria-label="ir a seccion"><a onclick="dpScroll(0)">①</a> <a onclick="dpScroll(1)">②</a> <a onclick="dpScroll(2)">③</a> <a onclick="dpScroll(3)">④</a> <a onclick="dpScroll(4)">⑤</a> <a onclick="dpScroll(5)">⑥</a></nav><div class="dp-section"><div class="dp-section-label" style="color:#818cf8"><span class="label-icon" style="background:rgba(99,102,241,0.15)">01</span>'+DL.s1+'</div><div class="dp-sowhat"><div class="dp-sowhat-q">'+DL.s1q+'</div><div class="dp-sowhat-a">'+ins.sowhat+'</div><div style="font-size:11px;color:#64748b;margin-top:4px">'+ins.sowhatSub+'</div></div>'+magicBar+'</div><div class="dp-section"><div class="dp-section-label" style="color:#f59e0b"><span class="label-icon" style="background:rgba(245,158,11,0.15)">02</span>'+DL.s2+'</div><div class="dp-verdict '+verdictClass+'"><div class="dp-verdict-label">'+DL.vl+'</div><div class="dp-verdict-text" style="color:'+decisionColor+'">'+ins.decision+'</div><div class="dp-verdict-sub">'+s.verdictText+'</div></div><div class="dp-matrix"><div class="dp-matrix-cell highlight"><div class="dp-mc-label">'+DL.cs+'</div><div class="dp-mc-value" style="color:'+(ins.isTractable?'#10b981':'#ef4444')+'">'+(ins.isTractable?DL.viable:DL.noeff)+'</div><div class="dp-mc-sub">Stim/quimb/cotengra</div></div><div class="dp-matrix-cell"><div class="dp-mc-label">QPU hardware</div><div class="dp-mc-value" style="color:'+(ins.isIntractable?'#10b981':'#64748b')+'">'+(ins.isIntractable?DL.consider:DL.notreq)+'</div><div class="dp-mc-sub">IBM/Google/IonQ</div></div><div class="dp-matrix-cell"><div class="dp-mc-label">'+DL.hpc+'</div><div class="dp-mc-value" style="color:'+(s.tw>20?'#ef4444':'#f59e0b')+'">'+(s.tw>20?DL.costhi:DL.ok2)+'</div><div class="dp-mc-sub">TW=2^'+s.tw+'</div></div><div class="dp-matrix-cell"><div class="dp-mc-label">'+DL.te+'</div><div class="dp-mc-value">'+(ins.isTractable?'< 1s':DL.tbd)+'</div><div class="dp-mc-sub">'+(ins.isTractable?(EN?'local CPU':'CPU local'):(EN?'per platform':'segun plataforma'))+'</div></div></div></div><div class="dp-section"><div class="dp-section-label" style="color:#10b981"><span class="label-icon" style="background:rgba(16,185,129,0.15)">03</span>'+DL.s3+'</div>'+assumpHTML+bdHTML+'<div class="dp-money">'+moneyHTML+'</div></div><div class="dp-section"><div class="dp-section-label" style="color:#94a3b8"><span class="label-icon" style="background:rgba(255,255,255,0.06)">04</span>'+DL.s4+'</div><div class="dp-sci">'+sciHTML+'</div></div><div class="dp-section"><div class="dp-section-label" style="color:#c7d2fe"><span class="label-icon" style="background:rgba(99,102,241,0.15)">05</span>'+DL.s5+'</div><div class="dp-rec"><div class="dp-rec-title">'+DL.rt+'</div><div class="dp-rec-text">'+ins.rec.text+'</div><div class="dp-rec-action">'+recActHTML+'</div></div></div>'+sec06:'<div class="dp-section" style="color:#475569;font-size:13px;text-align:center;padding:40px 0">'+DL.empty+'</div>')+'</div>'+limFoot+'<div class="dp-footer"><span>'+DL.foot+'</span><span>'+new Date().toLocaleTimeString()+'</span></div>';
  var cb=document.getElementById('dp-close-btn');if(cb)cb.addEventListener('click',function(){document.getElementById('decision-panel').classList.remove('open');var t=$('decision-toggle');if(t)t.setAttribute('aria-expanded','false');});
  panel.querySelectorAll('.dp-rec-btn').forEach(function(b){b.addEventListener('click',function(){decisionAction(b.getAttribute('data-act')||'');});});
  wireEconControls();
}
function dpScroll(i){var s=document.querySelectorAll('#decision-panel .dp-section')[i];if(s)s.scrollIntoView({behavior:'smooth',block:'start'});}   // R6
// R1 — handle de redimensionado top-tier (6 bugs cubiertos)
function setupResize(){
  var h=document.getElementById('rsz'),ob=document.getElementById('outbody');if(!h||!ob)return;
  try{var sv=localStorage.getItem('atlas-outh');if(sv&&+sv>=120)ob.style.height=(+sv)+'px';}catch(e){}   // (5) persistencia
  function mainH(){var m=document.querySelector('main.main');return m?m.clientHeight:600;}
  function clamp(px){return Math.max(120,Math.min(mainH()-180,px));}                                    // (3) clamp min/max
  function save(){try{localStorage.setItem('atlas-outh',parseInt(ob.style.height)||210);}catch(e){}}
  var on=false,sy=0,sh=0;
  h.addEventListener('pointerdown',function(e){on=true;sy=e.clientY;sh=ob.getBoundingClientRect().height;
    try{h.setPointerCapture(e.pointerId);}catch(_){}                                                    // (2) pointer capture
    document.body.style.userSelect='none';document.body.style.cursor='row-resize';h.classList.add('drag');e.preventDefault();});  // (1) sin seleccion de texto
  h.addEventListener('pointermove',function(e){if(!on)return;ob.style.height=clamp(sh+(sy-e.clientY))+'px';});  // (4) el gutter de lineas queda sincronizado por flex (edwrap flex:1)
  function end(e){if(!on)return;on=false;document.body.style.userSelect='';document.body.style.cursor='';h.classList.remove('drag');try{h.releasePointerCapture(e.pointerId);}catch(_){}save();}
  h.addEventListener('pointerup',end);h.addEventListener('pointercancel',end);
  h.addEventListener('keydown',function(e){var c=ob.getBoundingClientRect().height;                     // a11y: flechas mueven el separador
    if(e.key==='ArrowUp'){ob.style.height=clamp(c+24)+'px';e.preventDefault();save();}
    if(e.key==='ArrowDown'){ob.style.height=clamp(c-24)+'px';e.preventDefault();save();}});
}
window.addEventListener('load',function(){
  setupResize();
  if(typeof updateStepper==='function')updateStepper();   // V2-3: estado inicial del stepper
  var tg=document.getElementById('decision-toggle');
  if(tg)tg.addEventListener('click',function(){buildDecisionPanel();var p=document.getElementById('decision-panel');var op=p.classList.toggle('open');tg.setAttribute('aria-expanded',op?'true':'false');});
  // R10 onboarding (primera visita)
  if(!localStorage.getItem('atlas-onboarded')){var t=document.createElement('div');t.id='onbtip';
    t.innerHTML=(LANG==='en'?'Atlas runs operational diagnostics for classical simulability. It reports indicators, not certified quantum advantage.':'Atlas corre diagnosticos operacionales de simulabilidad clasica. Reporta indicadores, no ventaja cuantica certificada.')+'<br><button onclick="this.closest(\'#onbtip\').remove();try{localStorage.setItem(\'atlas-onboarded\',\'1\')}catch(e){}">'+(LANG==='en'?'Got it':'Entendido')+'</button>';
    document.body.appendChild(t);setTimeout(function(){var x=document.getElementById('onbtip');if(x)x.remove();try{localStorage.setItem('atlas-onboarded','1')}catch(e){}},6500);}
  var logEl=document.getElementById('pLog');
  if(logEl)new MutationObserver(function(){var p=document.getElementById('decision-panel');
    if(p&&p.classList.contains('open'))setTimeout(function(){buildDecisionPanel();document.getElementById('decision-panel').classList.add('open');},300);
  }).observe(logEl,{characterData:true,childList:true,subtree:true});
});
// ===== END DECISION PANEL =====
</script>
<button id="decision-toggle" aria-label="Abrir recomendacion de siguiente accion" aria-expanded="true" aria-controls="decision-panel" title="Que hacer ahora: decision estrategica / plataforma / economica / tecnica (Esc para cerrar)">WHAT NEXT</button>
<style id="an-css">
body.modal-open{overflow:hidden!important}
/* #6/#8/#10 responsive: keep the 2D map and triage usable below ~1200px wide */
@media(max-width:1200px){
  .side{width:330px}
  .landscape-grid{grid-template-columns:1fr!important}   /* map full width, legend stacks below */
  .landscape-card #phase{min-height:240px}
}
@media(max-width:980px){
  body{overflow:auto}
  .app{flex-direction:column;height:auto;min-height:calc(100% - 84px)}
  .side{width:100%;order:3;max-height:none}
  .main{order:1;min-height:70vh}
  .worktop{flex-direction:column;min-height:0}
  .edwrap,.worksum{flex:1 1 auto;min-height:220px}
  #circ-inline{max-height:none}
}
#atlas-toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(12px);z-index:22000;background:#161620;border:1px solid var(--vio);color:#e2e8f0;border-radius:8px;padding:9px 16px;font:600 12px 'IBM Plex Sans';box-shadow:0 10px 30px rgba(0,0,0,.5);opacity:0;pointer-events:none;transition:opacity .2s,transform .2s}
#atlas-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
#atlas-toast.err{border-color:var(--red);color:#fecaca}
#analysis-modal{position:fixed;inset:0;background:rgba(0,0,0,.62);z-index:21000;display:none;align-items:center;justify-content:center;padding:20px}
#analysis-modal.open{display:flex}
.an-card-wrap{background:var(--surface);border:1px solid var(--vio);border-radius:12px;max-width:880px;width:100%;max-height:88vh;overflow:auto;box-shadow:0 20px 60px rgba(0,0,0,.6)}
.an-top{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--bd);position:sticky;top:0;background:var(--surface);z-index:1}
.an-top h3{margin:0;font:800 13px 'IBM Plex Sans';color:#e2e8f0;letter-spacing:.02em}
.an-x{background:transparent;border:1px solid var(--bd);color:var(--text2);border-radius:6px;padding:4px 9px;cursor:pointer}
.an-x:hover{background:rgba(248,113,113,.15);color:var(--red)}
.an-body{padding:16px}
.an-head{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:14px}
.an-route{font:900 22px 'IBM Plex Sans';letter-spacing:.04em}
.an-route.ok{color:#34d399}.an-route.maybe{color:#fb923c}.an-route.no{color:#fb7185}
.an-sub{font:11px 'JetBrains Mono';color:#64748b;margin-top:2px}
.an-score{text-align:right;font:900 28px 'IBM Plex Sans';color:#e2e8f0}.an-score span{font-size:13px;color:#64748b}
.an-conf{font:11px 'IBM Plex Sans';color:#94a3b8;font-weight:600}
.an-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.an-card{border:1px solid var(--bd);background:rgba(255,255,255,.02);border-radius:9px;padding:12px}
.an-card h4{margin:0 0 8px;font:800 11px 'IBM Plex Sans';text-transform:uppercase;letter-spacing:.06em;color:#a78bfa}
.an-card p{margin:4px 0;font:12px 'IBM Plex Sans';color:#cbd5e1;line-height:1.4}
.an-card p.an-win{color:#34d399;font-weight:600;border-left:2px solid #34d399;padding-left:8px;margin-top:8px}
.an-card .ok{color:#34d399}.an-card .maybe{color:#fb923c}.an-card .no{color:#fb7185}
.an-list{margin:6px 0 0;padding-left:16px;font:11.5px 'IBM Plex Sans';color:#cbd5e1;line-height:1.5}
.an-tbl{width:100%;border-collapse:collapse;font:11.5px 'IBM Plex Sans'}
.an-tbl th{color:#64748b;font-weight:600;text-align:left;padding:3px 4px;border-bottom:1px solid var(--bd)}
.an-tbl td{padding:3px 4px;color:#cbd5e1;border-bottom:1px solid rgba(255,255,255,.04)}
.an-lit{margin-top:12px;border:1px solid rgba(99,102,241,.25);background:rgba(99,102,241,.05);border-radius:9px;padding:12px}
.an-lit h4{margin:0 0 6px;font:800 11px 'IBM Plex Sans';text-transform:uppercase;letter-spacing:.06em;color:#818cf8}
.an-lit p{margin:0;font:11.5px 'IBM Plex Sans';color:#94a3b8;line-height:1.5}
@media(max-width:680px){.an-grid{grid-template-columns:1fr}}
/* Fase 6: chat real (Claude) */
/* V2-8: chat como widget flotante (burbuja) abajo-derecha */
#chat-modal{position:fixed;right:22px;bottom:88px;z-index:21500;display:none;width:360px;max-width:calc(100vw - 36px)}
#chat-modal.open{display:block}
#chat-fab{position:fixed;right:22px;bottom:22px;z-index:21501;width:54px;height:54px;border-radius:50%;background:var(--accent);border:none;color:#fff;font-size:22px;cursor:pointer;box-shadow:0 8px 28px rgba(99,102,241,.5);transition:transform .15s,background .15s}
#chat-fab:hover{transform:translateY(-2px)}
#chat-fab.on{background:var(--surface2);border:1px solid var(--accent)}
.cm-card{background:var(--surface);border:1px solid var(--vio);border-radius:14px;width:100%;height:min(64vh,500px);display:flex;flex-direction:column;box-shadow:0 18px 50px rgba(0,0,0,.6)}
.cm-top{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--bd)}
.cm-top h3{margin:0;font:800 13px 'IBM Plex Sans';color:#e2e8f0;letter-spacing:.02em}
.cm-ctx{font:10.5px 'JetBrains Mono';color:#64748b;margin-top:2px}
.cm-log{flex:1;overflow:auto;padding:14px 16px;display:flex;flex-direction:column;gap:10px}
.cm-msg{max-width:86%;padding:9px 12px;border-radius:10px;font:12.5px/1.5 'IBM Plex Sans';white-space:pre-wrap;word-break:break-word}
.cm-msg.user{align-self:flex-end;background:rgba(99,102,241,.16);border:1px solid rgba(99,102,241,.35);color:#e2e8f0}
.cm-msg.bot{align-self:flex-start;background:rgba(255,255,255,.03);border:1px solid var(--bd);color:#cbd5e1}
.cm-msg.sys{align-self:center;text-align:center;background:transparent;color:#64748b;font-size:11px;max-width:100%}
.cm-msg.err{align-self:center;background:rgba(248,113,113,.1);border:1px solid var(--red);color:#fecaca;max-width:100%;text-align:center}
.cm-foot{display:flex;gap:8px;padding:12px 16px;border-top:1px solid var(--bd)}
.cm-foot textarea{flex:1;resize:none;background:var(--bg);border:1px solid var(--bd);border-radius:8px;color:#e2e8f0;padding:8px 10px;font:12.5px 'IBM Plex Sans';height:42px;max-height:120px}
.cm-foot textarea:focus{outline:none;border-color:var(--accent)}
.cm-send{background:var(--accent);border:0;color:#fff;border-radius:8px;padding:0 16px;font:700 12px 'IBM Plex Sans';cursor:pointer}
.cm-send:disabled{opacity:.5;cursor:default}
@media(max-width:680px){.an-grid{grid-template-columns:1fr}.cm-card{height:70vh}#chat-modal{width:calc(100vw - 24px);right:12px}}
/* V2-5: Modelo de Gasto drawer (slide-in derecho) */
#gasto-drawer{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:21800;display:none;justify-content:flex-end}
#gasto-drawer.open{display:flex}
.gd-card{width:430px;max-width:100vw;height:100%;background:var(--surface);border-left:1px solid var(--vio);box-shadow:-20px 0 60px rgba(0,0,0,.6);display:flex;flex-direction:column;animation:gdslide .24s cubic-bezier(.4,0,.2,1)}
@keyframes gdslide{from{transform:translateX(36px);opacity:.5}to{transform:translateX(0);opacity:1}}
.gd-top{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;border-bottom:1px solid var(--bd)}
.gd-top h3{margin:0;font:800 13px 'IBM Plex Sans';color:#e2e8f0;letter-spacing:.02em}
.gd-sub{font:10.5px 'JetBrains Mono',monospace;color:#64748b;margin-top:2px}
.gd-body{padding:14px 16px;overflow-y:auto;flex:1}
.gd-empty{color:#64748b;text-align:center;padding:34px 12px;font:12px 'IBM Plex Sans';line-height:1.5}
/* V2-0: command palette (Cmd-K) */
.cmdk-trigger{display:inline-flex;align-items:center;gap:8px;background:var(--surface2);border:1px solid var(--bd);color:var(--text2);border-radius:8px;padding:5px 10px;font:500 11.5px 'IBM Plex Sans';cursor:pointer}
.cmdk-trigger:hover{border-color:var(--accent);color:#e2e8f0}
.cmdk-trigger kbd{background:var(--bg);border:1px solid var(--bd);border-radius:4px;padding:1px 6px;font:600 10px 'JetBrains Mono';color:#94a3b8}
#cmdk{position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:22000;display:none;align-items:flex-start;justify-content:center;padding:12vh 20px}
#cmdk.open{display:flex}
.cmdk-box{background:var(--surface);border:1px solid var(--vio);border-radius:12px;max-width:560px;width:100%;box-shadow:0 24px 70px rgba(0,0,0,.6);overflow:hidden}
.cmdk-input{width:100%;background:var(--bg);border:0;border-bottom:1px solid var(--bd);color:#e2e8f0;padding:14px 16px;font:500 14px 'IBM Plex Sans';outline:none}
.cmdk-list{max-height:50vh;overflow:auto;padding:6px}
.cmdk-item{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:8px;cursor:pointer}
.cmdk-item.sel,.cmdk-item:hover{background:rgba(99,102,241,.16)}
.cmdk-g{font:600 9.5px 'JetBrains Mono',monospace;text-transform:uppercase;letter-spacing:.06em;color:#818cf8;min-width:78px}
.cmdk-l{font:13px 'IBM Plex Sans';color:#e2e8f0}
.cmdk-empty{padding:18px;text-align:center;color:#64748b;font:12px 'IBM Plex Sans'}
.cmdk-foot{padding:8px 14px;border-top:1px solid var(--bd);font:10.5px 'JetBrains Mono',monospace;color:#64748b}
@media(max-width:760px){.cmdk-trigger span{display:none}}
</style>
<div id="atlas-toast" role="status" aria-live="polite"></div>
<div id="analysis-modal" onclick="if(event.target===this)closeAnalysisPanel()">
  <div class="an-card-wrap">
    <div class="an-top"><h3>Atlas · análisis de triage</h3><button class="an-x" onclick="closeAnalysisPanel()" aria-label="Cerrar análisis">✕</button></div>
    <div class="an-body" id="analysis-body"></div>
  </div>
</div>
<div id="cmdk" onclick="if(event.target===this)closePalette()">
  <div class="cmdk-box" role="dialog" aria-label="Paleta de comandos">
    <input id="cmdk-input" class="cmdk-input" placeholder="Buscar acción… (analizar, generar, exportar, chat…)" aria-label="Buscar acción" autocomplete="off" oninput="_cmdkSel=0;renderCmdk(this.value)" onkeydown="cmdkKey(event)">
    <div class="cmdk-list" id="cmdk-list"></div>
    <div class="cmdk-foot">↑↓ navegar · ↵ ejecutar · esc cerrar</div>
  </div>
</div>
<div id="gasto-drawer" onclick="if(event.target===this)closeGastoDrawer()">
  <div class="gd-card" role="dialog" aria-label="Modelo de gasto">
    <div class="gd-top"><div><h3>＄ Modelo de Gasto</h3><div class="gd-sub" data-i18n=gdSub>Economía de rutas de cómputo</div></div><button class="an-x" onclick="closeGastoDrawer()" aria-label="Cerrar modelo de gasto">✕</button></div>
    <div class="gd-body" id="gasto-drawer-body"></div>
  </div>
</div>
<button id="chat-fab" onclick="toggleChatBubble()" aria-label="Abrir/cerrar chat con Claude" title="Ask Chat (Claude)">💬</button>
<div id="chat-modal">
  <div class="cm-card">
    <div class="cm-top"><div><h3 id="cm-title">Ask Chat · Claude</h3><div class="cm-ctx" id="cm-ctx"></div></div><button class="an-x" onclick="closeChat()" aria-label="Cerrar chat">✕</button></div>
    <div class="cm-privacy" style="font-size:10px;color:#f6ad55;background:rgba(246,173,85,.08);border:1px solid rgba(246,173,85,.25);border-radius:6px;padding:6px 9px;margin:0 0 6px;line-height:1.4">⚠ Aviso: este chat envía tu circuito (QASM) y su diagnóstico a la API de Claude (Anthropic), un servicio externo. No lo uses con circuitos confidenciales. El veredicto de Atlas es 100% local; solo este chat opcional sale del equipo.</div>
    <div class="cm-log" id="cm-log"></div>
    <div class="cm-foot">
      <textarea id="cm-input" rows=1 placeholder="Pregunta sobre el diagnóstico… (Enter envía)" aria-label="Mensaje al chat" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();chatSend();}"></textarea>
      <button class="cm-send" id="cm-send" onclick="chatSend()">Enviar</button>
    </div>
  </div>
</div>
<div id="builder-modal">
  <div class="bm-card lab">
    <div class="bm-head"><span>⊞ <span data-i18n=builderTitle>Constructor visual de circuitos</span></span><button class="bm-x" onclick="closeBuilder()" aria-label="Cerrar constructor">✕</button></div>
    <div class="bm-toolbar">
      <button class=bm-tb onclick="bUndo()" aria-label="Deshacer" title="Deshacer">←</button>
      <button class=bm-tb id=bm-stateview onclick="bToggleState()" aria-label="Ver probabilidades y Q-sphere" title="Probabilities + Q-sphere (estado del circuito, n<=7)">📊</button>
      <button class=bm-tb id=bm-measure onclick="bMeasure()" aria-label="Medir spread, MPS y treewidth" title="Measure: spread / MPS / treewidth / route (backend quimb+cotengra)">📐</button>
      <span class=bm-tlabel data-i18n=builderN2>n qubits</span>
      <input id="builder-n" type=range min=1 max=16 value=4 oninput="bSetN(this.value)" class=bm-nslider aria-label="numero de qubits">
      <span id=bm-nval class=bm-nval>4</span>
      <span class=bm-tlabel title="Angulo para Rx/Ry/Rz">θ</span>
      <input id="builder-theta" class="bm-angle" value="pi/4" aria-label="angulo para rotaciones Rx Ry Rz" oninput="bStatus()">
      <span class="sp"></span>
      <span id="builder-status" class="bm-status"></span>
    </div>
    <div class="bm-lab">
      <div class="bm-palette" id="builder-pal"></div>
      <div class="bm-canvas" id="builder-circ"></div>
      <div class="bm-canvas" id="builder-state" style="display:none"></div>
    </div>
    <div class="bm-foot">
      <div class="bm-metrics" id="builder-metrics"></div>
      <div class="bm-metrics" id="builder-measure" style="margin-top:4px"></div>
      <div class="bm-divider"></div>
      <textarea id="builder-qasm-preview" class="bm-qasm" readonly title="el QASM se genera automaticamente — editalo en el editor principal"></textarea>
      <div class="bm-divider"></div>
      <div class="bm-actions"><button class=tool onclick="bClear()" data-i18n=builderClear>Limpiar</button><button class="tool hero" onclick="bUse()" data-i18n=builderUse>&#9654; Usar y analizar</button></div>
    </div>
  </div>
</div>
<style id="atlas-lm-css">
#atlas-lm-btn{position:relative;z-index:9999;border:1px solid var(--bd);color:var(--text2);background:transparent;border-radius:6px;padding:3px 11px;margin:0 10px;font:500 11px 'IBM Plex Sans';letter-spacing:.04em;cursor:pointer;transition:background .15s,color .15s,border-color .15s}
#atlas-lm-btn:hover,#atlas-lm-btn.on{background:var(--vio);border-color:var(--vio);color:#fff}
body.layout-mode{cursor:default}
body.layout-mode .main,body.layout-mode .side{opacity:.12;pointer-events:none;transition:opacity .2s}
body.layout-mode .topbar{opacity:.6}
#atlas-lm-backdrop{position:fixed;inset:0;z-index:8000;background:rgba(5,5,10,.45);opacity:0;pointer-events:none;transition:opacity .2s}
body.layout-mode #atlas-lm-backdrop{opacity:1;backdrop-filter:blur(2px);-webkit-backdrop-filter:blur(2px)}
.atlas-fp{position:fixed;z-index:8500;background:var(--surface);border:1px solid var(--vio);border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,.55),0 0 0 1px rgba(139,92,246,.15);overflow:hidden;display:flex;flex-direction:column;min-width:160px;min-height:80px;transition:box-shadow .15s;animation:atlasFpIn .15s ease-out both}
.atlas-fp:hover{box-shadow:0 12px 40px rgba(0,0,0,.65),0 0 0 2px rgba(139,92,246,.35)}
.atlas-fp.dragging{box-shadow:0 18px 50px rgba(0,0,0,.7),0 0 0 2px rgba(139,92,246,.5);opacity:.95;will-change:transform}
@keyframes atlasFpIn{from{opacity:0;transform:scale(.96)}to{opacity:1;transform:scale(1)}}
.atlas-fp-bar{background:rgba(139,92,246,.12);border-bottom:1px solid var(--bd);padding:5px 8px;display:flex;align-items:center;gap:6px;cursor:grab;user-select:none}
.atlas-fp-bar:active{cursor:grabbing}
.atlas-fp-bar:focus-visible{outline:2px solid var(--vio2);outline-offset:-2px}
.atlas-fp-icon{font-size:12px;opacity:.7;line-height:1}
.atlas-fp-title{font:600 10px 'IBM Plex Sans';text-transform:uppercase;letter-spacing:.06em;color:#a78bfa;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.atlas-fp-actions{display:flex;gap:2px}
.atlas-fp-btn{background:transparent;border:1px solid transparent;border-radius:4px;color:var(--text2);padding:2px 5px;font-size:11px;line-height:1;cursor:pointer;transition:background .12s,color .12s}
.atlas-fp-btn:hover{background:rgba(255,255,255,.08);color:#fff}
.atlas-fp-btn.minimize-btn:hover{background:rgba(251,191,36,.15);color:var(--warn)}
.atlas-fp-btn.restore-btn:hover{background:rgba(248,113,113,.15);color:var(--red)}
.atlas-fp-content{flex:1;overflow:auto;min-height:0;position:relative}
.atlas-fp-content>*{height:100%}
.atlas-fp-resize{position:absolute;right:0;bottom:0;width:14px;height:14px;cursor:nwse-resize;z-index:2}
.atlas-fp-resize::after{content:'';position:absolute;right:2px;bottom:2px;width:8px;height:8px;border-right:2px solid var(--vio2);border-bottom:2px solid var(--vio2);opacity:.5}
.atlas-fp:hover .atlas-fp-resize::after{opacity:1}
.atlas-fp.fp-minimized{height:auto!important;min-height:unset!important}
.atlas-fp.fp-minimized .atlas-fp-content,.atlas-fp.fp-minimized .atlas-fp-resize{display:none}
.atlas-fp.fp-minimized .atlas-fp-bar{background:rgba(139,92,246,.22)}
#atlas-lm-tray{position:fixed;bottom:8px;left:50%;transform:translateX(-50%);z-index:9998;display:none;gap:6px;flex-wrap:wrap;justify-content:center;max-width:80vw}
#atlas-lm-tray.has-minimized{display:flex}
.atlas-lm-pill{background:var(--surface2);border:1px solid var(--vio);border-radius:20px;color:var(--vio2);font:600 10px 'IBM Plex Sans';text-transform:uppercase;letter-spacing:.05em;padding:3px 12px;cursor:pointer;transition:background .12s}
.atlas-lm-pill:hover{background:rgba(139,92,246,.2)}
</style>
<script id="atlas-lm-js">
(function(){
'use strict';
if(window.__atlasLM)return;
var STORAGE_KEY='atlas_lm_v1',SNAP=20,Z_BASE=8500,Z_TOP=8600;
var DEFS=[
  {id:'fp-editor',icon:'⌨',title:'Editor QASM',sel:'[data-lm="editor"]',def:{left:20,top:90,w:520,h:340}},
  {id:'fp-output',icon:'⚡',title:'Output / Circuito',sel:'[data-lm="output"]',head:'[data-lm="output-head"]',def:{left:20,top:450,w:520,h:220}},
  {id:'fp-explorer',icon:'🔬',title:'Design Explorer',sel:'[data-lm="explorer"]',def:{left:555,top:90,w:420,h:380}},
  {id:'fp-decision',icon:'🧠',title:'Decision',sel:'[data-lm="decision"]',def:{left:990,top:90,w:400,h:520}},
  {id:'fp-summary',icon:'📊',title:'Summary / Triage',sel:'[data-lm="summary"]',def:{left:555,top:485,w:420,h:200}}
];
var state={active:false,order:[],recs:{},drag:null,resize:null,saved:{}};
function q(s,r){return (r||document).querySelector(s);}
function depth(el){var d=0;while(el){el=el.parentElement;d++;}return d;}
function clampPos(p){return {left:Math.min(Math.max(0,p.left),window.innerWidth-80),top:Math.min(Math.max(48,p.top),window.innerHeight-40),width:p.width,height:p.height};}
function loadState(){try{return JSON.parse(localStorage.getItem(STORAGE_KEY))||{};}catch(e){return {};}}
function saveState(){var s={};state.order.forEach(function(id){var r=state.recs[id];if(r)s[id]={left:r.pos.left,top:r.pos.top,width:r.pos.width,height:r.pos.height,minimized:!!r.minimized};});try{localStorage.setItem(STORAGE_KEY,JSON.stringify(s));}catch(e){}}
function captureMove(el,content){var rec={el:el,parent:el.parentNode,next:el.nextSibling,style:el.getAttribute('style')};content.appendChild(el);return rec;}
function restoreEl(m){var anchor=(m.next&&m.next.parentNode===m.parent)?m.next:null;if(anchor)m.parent.insertBefore(m.el,anchor);else m.parent.appendChild(m.el);if(m.style===null)m.el.removeAttribute('style');else m.el.setAttribute('style',m.style);}
function createPanel(def,idx){
  var prim=q(def.sel);if(!prim)return null;
  var els=[];if(def.head){var h=q(def.head);if(h)els.push(h);}els.push(prim);
  var fp=document.createElement('div');fp.className='atlas-fp';fp.id=def.id;
  fp.setAttribute('role','dialog');fp.setAttribute('aria-label',def.title);fp.style.animationDelay=(idx*30)+'ms';
  var saved=state.saved[def.id]||{};
  var pos=clampPos({left:saved.left!=null?saved.left:def.def.left,top:saved.top!=null?saved.top:def.def.top,width:saved.width!=null?saved.width:def.def.w,height:saved.height!=null?saved.height:def.def.h});
  fp.style.left=pos.left+'px';fp.style.top=pos.top+'px';fp.style.width=pos.width+'px';fp.style.height=pos.height+'px';fp.style.zIndex=Z_BASE;
  var bar=document.createElement('div');bar.className='atlas-fp-bar';bar.setAttribute('tabindex','0');bar.setAttribute('role','toolbar');bar.setAttribute('aria-label',def.title+' — drag, or arrow keys to move');
  bar.innerHTML='<span class="atlas-fp-icon" aria-hidden="true">'+def.icon+'</span><span class="atlas-fp-title">'+def.title+'</span><div class="atlas-fp-actions"><button class="atlas-fp-btn minimize-btn" type="button" title="Minimizar" aria-label="Minimizar panel">─</button><button class="atlas-fp-btn restore-btn" type="button" title="Restaurar al layout" aria-label="Devolver panel al layout original">✕</button></div>';
  var content=document.createElement('div');content.className='atlas-fp-content';
  var rsz=document.createElement('div');rsz.className='atlas-fp-resize';rsz.setAttribute('aria-hidden','true');
  fp.appendChild(bar);fp.appendChild(content);fp.appendChild(rsz);document.body.appendChild(fp);
  var moves=els.map(function(e){return captureMove(e,content);});
  var rec={id:def.id,def:def,fp:fp,content:content,bar:bar,moves:moves,minimized:!!saved.minimized,pos:pos};
  state.recs[def.id]=rec;
  bar.addEventListener('mousedown',function(e){onBarDown(e,rec);});
  bar.addEventListener('keydown',function(e){onBarKey(e,rec);});
  rsz.addEventListener('mousedown',function(e){onResizeDown(e,rec);});
  fp.addEventListener('mousedown',function(){bringToFront(rec);},true);
  bar.querySelector('.minimize-btn').addEventListener('click',function(e){e.stopPropagation();toggleMin(rec);});
  bar.querySelector('.restore-btn').addEventListener('click',function(e){e.stopPropagation();restorePanel(rec.id);});
  if(rec.minimized){fp.classList.add('fp-minimized');bar.querySelector('.minimize-btn').textContent='▢';}
  return rec;
}
function restorePanel(id){var rec=state.recs[id];if(!rec)return;for(var i=rec.moves.length-1;i>=0;i--)restoreEl(rec.moves[i]);rec.fp.remove();delete state.recs[id];state.order=state.order.filter(function(x){return x!==id;});updateTray();saveState();}
function bringToFront(rec){state.order.forEach(function(id){var r=state.recs[id];if(r)r.fp.style.zIndex=Z_BASE;});rec.fp.style.zIndex=Z_TOP;}
function toggleMin(rec){rec.minimized=!rec.minimized;rec.fp.classList.toggle('fp-minimized',rec.minimized);rec.bar.querySelector('.minimize-btn').textContent=rec.minimized?'▢':'─';updateTray();saveState();}
function updateTray(){var tray=q('#atlas-lm-tray');if(!tray)return;var mins=state.order.map(function(id){return state.recs[id];}).filter(function(r){return r&&r.minimized;});tray.innerHTML='';mins.forEach(function(r){var pill=document.createElement('button');pill.type='button';pill.className='atlas-lm-pill';pill.textContent=r.def.icon+' '+r.def.title;pill.addEventListener('click',function(){toggleMin(r);bringToFront(r);});tray.appendChild(pill);});tray.classList.toggle('has-minimized',mins.length>0);}
function onBarDown(e,rec){if(e.button!==0)return;if(e.target.closest('button,input,select,textarea,a,[contenteditable="true"]'))return;bringToFront(rec);var r=rec.fp.getBoundingClientRect();state.drag={rec:rec,sx:e.clientX,sy:e.clientY,left:r.left,top:r.top};rec.fp.classList.add('dragging');rec.fp.style.transition='none';e.preventDefault();}
function onMouseMove(e){
  if(state.drag){var d=state.drag,c=clampPos({left:d.left+(e.clientX-d.sx),top:d.top+(e.clientY-d.sy),width:d.rec.pos.width,height:d.rec.pos.height});d.rec.fp.style.transform='translate('+(c.left-d.left)+'px,'+(c.top-d.top)+'px)';d.c=c;}
  else if(state.resize){var z=state.resize,nw=Math.max(160,z.w+(e.clientX-z.sx)),nh=Math.max(80,z.h+(e.clientY-z.sy));z.rec.fp.style.width=nw+'px';z.rec.fp.style.height=nh+'px';z.rec.pos.width=nw;z.rec.pos.height=nh;}
}
function onMouseUp(){
  if(state.drag){var d=state.drag,c=d.c||clampPos({left:d.left,top:d.top,width:d.rec.pos.width,height:d.rec.pos.height});var sl=Math.round(c.left/SNAP)*SNAP,st=Math.round(c.top/SNAP)*SNAP;d.rec.fp.style.transform='';d.rec.fp.style.transition='left .08s ease-out,top .08s ease-out';d.rec.fp.style.left=sl+'px';d.rec.fp.style.top=st+'px';d.rec.pos.left=sl;d.rec.pos.top=st;d.rec.fp.classList.remove('dragging');var fp=d.rec.fp;setTimeout(function(){if(fp)fp.style.transition='box-shadow .15s';},120);state.drag=null;saveState();}
  if(state.resize){state.resize=null;saveState();}
}
function onResizeDown(e,rec){if(e.button!==0)return;bringToFront(rec);var r=rec.fp.getBoundingClientRect();state.resize={rec:rec,sx:e.clientX,sy:e.clientY,w:r.width,h:r.height};e.preventDefault();e.stopPropagation();}
function onBarKey(e,rec){var step=e.shiftKey?SNAP*2:SNAP,dx=0,dy=0;if(e.key==='ArrowLeft')dx=-step;else if(e.key==='ArrowRight')dx=step;else if(e.key==='ArrowUp')dy=-step;else if(e.key==='ArrowDown')dy=step;else return;e.preventDefault();var c=clampPos({left:rec.pos.left+dx,top:rec.pos.top+dy,width:rec.pos.width,height:rec.pos.height});rec.fp.style.left=c.left+'px';rec.fp.style.top=c.top+'px';rec.pos.left=c.left;rec.pos.top=c.top;bringToFront(rec);saveState();}
function activate(){
  state.active=true;state.saved=loadState();
  var btn=q('#atlas-lm-btn');if(btn){btn.classList.add('on');btn.textContent='⊞ Exit Layout';}
  document.body.classList.add('layout-mode');
  var present=DEFS.map(function(def){var el=q(def.sel);return el?{def:def,d:depth(el)}:null;}).filter(Boolean);
  present.sort(function(a,b){return b.d-a.d;});
  state.order=[];
  present.forEach(function(p,i){var rec=createPanel(p.def,i);if(rec)state.order.push(rec.id);});
  updateTray();
}
function deactivate(){
  state.order.slice().reverse().forEach(function(id){var rec=state.recs[id];if(!rec)return;for(var i=rec.moves.length-1;i>=0;i--)restoreEl(rec.moves[i]);rec.fp.remove();delete state.recs[id];});
  state.order=[];state.active=false;
  document.body.classList.remove('layout-mode');
  var btn=q('#atlas-lm-btn');if(btn){btn.classList.remove('on');btn.textContent='⊞ Layout';}
  updateTray();
}
function toggle(){if(state.active)deactivate();else activate();}
function init(){
  if(q('#atlas-lm-btn'))return;
  var bar=q('.topbar'),badges=bar&&q('.badges',bar);
  var btn=document.createElement('button');btn.id='atlas-lm-btn';btn.type='button';btn.textContent='⊞ Layout';btn.setAttribute('aria-label','Layout Mode: paneles flotantes reordenables');btn.addEventListener('click',toggle);
  if(bar&&badges)bar.insertBefore(btn,badges);else if(bar)bar.appendChild(btn);
  var bd=document.createElement('div');bd.id='atlas-lm-backdrop';document.body.appendChild(bd);
  var tray=document.createElement('div');tray.id='atlas-lm-tray';document.body.appendChild(tray);
  document.addEventListener('mousemove',onMouseMove);
  document.addEventListener('mouseup',onMouseUp);
  window.addEventListener('resize',function(){if(!state.active)return;state.order.forEach(function(id){var r=state.recs[id];if(!r)return;var c=clampPos(r.pos);r.fp.style.left=c.left+'px';r.fp.style.top=c.top+'px';r.pos.left=c.left;r.pos.top=c.top;});});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
window.__atlasLM={toggle:toggle,activate:activate,deactivate:deactivate,state:state};
})();
</script>
<!-- Kreniq floating 3D background (Red de Transiciones) — Three.js r128 VENDORIZADO (offline, sin CDN) -->
<script src="/vendor/three-r128/three.min.js"></script>
<script src="/vendor/three-r128/OrbitControls.js"></script>
<script>
(function(){
  if(typeof THREE==='undefined'){return;}        // CDN bloqueado/offline -> sin fondo, app intacta
  try{
    const container = document.getElementById('kreniq-bg');
    const scene = new THREE.Scene();
    scene.background = null;                       // transparente -> deja ver html #05060A
    scene.fog = new THREE.FogExp2('#000000', 0.008);   // CAPAS: fog negro (logo_kreniq_volum_trico)
    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 10, 80);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.appendChild(renderer.domElement);
    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true; controls.dampingFactor = 0.04;
    controls.autoRotate = true; controls.autoRotateSpeed = 0.8;
    controls.enablePan = false; controls.minDistance = 30; controls.maxDistance = 150;
    const matrixGroup = new THREE.Group(); scene.add(matrixGroup);
    const COLOR_NODE_GOLD=0xF5A623, COLOR_NODE_ORANGE=0xFF5722, COLOR_EDGE_CYAN=0x00E5FF, COLOR_EDGE_MAGENTA=0xE61062;
    const RADIUS=25, TOTAL_NODES=36;
    const nodes=[]; const phi=Math.PI*(3-Math.sqrt(5));
    for(let i=0;i<TOTAL_NODES;i++){
      const y=1-(i/(TOTAL_NODES-1))*2; const radiusAtY=Math.sqrt(1-y*y); const theta=phi*i;
      const x=Math.cos(theta)*radiusAtY, z=Math.sin(theta)*radiusAtY;
      const pos=new THREE.Vector3(x*RADIUS,y*RADIUS,z*RADIUS);
      let weight=Math.random(); let isAttractor=weight>0.85;
      let nodeSize=isAttractor?(Math.random()*1.5+1.5):(Math.random()*0.8+0.4);
      nodes.push({pos,isAttractor,size:nodeSize,id:i});
    }
    const nodeMatStandard=new THREE.MeshBasicMaterial({color:COLOR_NODE_GOLD});
    const nodeMatAttractor=new THREE.MeshBasicMaterial({color:COLOR_NODE_ORANGE});
    nodes.forEach(node=>{
      const g=new THREE.Group(); g.position.copy(node.pos);
      const coreMaterial=node.isAttractor?nodeMatAttractor:nodeMatStandard;
      const core=new THREE.Mesh(new THREE.SphereGeometry(node.size,16,16),coreMaterial);
      g.add(core); matrixGroup.add(g);
    });
    const thickCyanMat=new THREE.MeshBasicMaterial({color:COLOR_EDGE_CYAN,transparent:true,opacity:0.8});
    const thickMagentaMat=new THREE.MeshBasicMaterial({color:COLOR_EDGE_MAGENTA,transparent:true,opacity:0.9});
    const thinCyanMat=new THREE.LineBasicMaterial({color:COLOR_EDGE_CYAN,transparent:true,opacity:0.25});
    function createTransitionEdge(nodeA,nodeB,type){
      const midPoint=new THREE.Vector3().addVectors(nodeA.pos,nodeB.pos).multiplyScalar(0.5);
      midPoint.multiplyScalar(0.3);
      const curve=new THREE.QuadraticBezierCurve3(nodeA.pos,midPoint,nodeB.pos);
      if(type==='thick_cyan'||type==='magenta'){
        const tubeGeo=new THREE.TubeGeometry(curve,32,type==='magenta'?0.4:0.25,6,false);
        const mat=type==='magenta'?thickMagentaMat:thickCyanMat;
        matrixGroup.add(new THREE.Mesh(tubeGeo,mat));
      }else{
        const points=curve.getPoints(20);
        const lineGeo=new THREE.BufferGeometry().setFromPoints(points);
        matrixGroup.add(new THREE.Line(lineGeo,thinCyanMat));
      }
    }
    const attractors=nodes.filter(n=>n.isAttractor);
    for(let i=0;i<attractors.length;i++)for(let j=i+1;j<attractors.length;j++){ if(Math.random()>0.3) createTransitionEdge(attractors[i],attractors[j],'thick_cyan'); }
    const magentaLoopLength=8; const magentaLoopNodes=[];
    for(let i=0;i<magentaLoopLength;i++) magentaLoopNodes.push(nodes[Math.floor(Math.random()*nodes.length)]);
    for(let i=0;i<magentaLoopLength;i++){ let nA=magentaLoopNodes[i],nB=magentaLoopNodes[(i+1)%magentaLoopLength]; if(nA!==nB) createTransitionEdge(nA,nB,'magenta'); }
    for(let i=0;i<TOTAL_NODES;i++){ let connections=Math.floor(Math.random()*3)+2; for(let c=0;c<connections;c++){ let target=nodes[Math.floor(Math.random()*nodes.length)]; if(nodes[i]!==target) createTransitionEdge(nodes[i],target,'thin'); } }
    const shellMesh=new THREE.Mesh(new THREE.SphereGeometry(RADIUS,24,24),new THREE.MeshBasicMaterial({color:0x444C56,transparent:true,opacity:0.03,wireframe:true}));
    matrixGroup.add(shellMesh);
    window.addEventListener('resize',function(){ camera.aspect=window.innerWidth/window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth,window.innerHeight); },false);
    (function loop(){ requestAnimationFrame(loop); controls.update(); matrixGroup.position.y=Math.sin(Date.now()*0.001)*1.5; renderer.render(scene,camera); })();
  }catch(e){ /* fondo es decorativo: nunca rompe la app */ }
})();
</script>
</body></html>"""


def _render_gates(circ, n=8, cap=None):
    """Lista de compuertas para dibujar el circuito en el cliente (JSON-serializable, acotada).
    Cap DINAMICO por n_qubits: ~35 gates por qubit visible -> circuitos normales (n<=8) y la mayoria de
    intractables (n=26 -> 910 > 783) se muestran ENTEROS; solo los masivos se truncan (proteccion del render)."""
    if cap is None:
        cap = max(300, n * 35)
    out = []
    for g in circ[:cap]:
        op = g[0]
        if op in ("cx", "cnot", "cz", "swap"):
            out.append([("cx" if op == "cnot" else op), g[1], g[2]])
        elif op == "rz":
            out.append(["rz", g[1]])
        elif len(g) >= 2:
            out.append([op, g[1]])
    return {"gates": out, "total": len(circ), "truncated": len(circ) > cap}


def _to_qir(n, circ):
    """Emite QIR textual (LLVM IR, base profile) desde el circuito normalizado de safe_parse.
    Mapea el gate set {h,x,y,z,s,sdg,t,tdg,cx,cz,swap} a las funciones __quantum__qis__*."""
    def Q(i): return f"%Qubit* inttoptr (i64 {i} to %Qubit*)"
    def R(i): return f"%Result* inttoptr (i64 {i} to %Result*)"
    S1 = {"h": "h__body", "x": "x__body", "y": "y__body", "z": "z__body", "s": "s__body",
          "t": "t__body", "sdg": "s__adj", "tdg": "t__adj"}
    body, skipped = [], set()
    for g in circ:
        op = g[0]
        if op in S1:
            body.append(f"  call void @__quantum__qis__{S1[op]}({Q(g[1])})")
        elif op in ("cx", "cnot"):
            body.append(f"  call void @__quantum__qis__cnot__body({Q(g[1])}, {Q(g[2])})")
        elif op == "cz":
            body.append(f"  call void @__quantum__qis__cz__body({Q(g[1])}, {Q(g[2])})")
        elif op == "swap":
            body.append(f"  call void @__quantum__qis__swap__body({Q(g[1])}, {Q(g[2])})")
        else:
            skipped.add(op)
    for i in range(n):                                    # medicion de todo el registro (base profile)
        body.append(f"  call void @__quantum__qis__mz__body({Q(i)}, {R(i)})")
    decls = "\n".join(
        "declare void @__quantum__qis__%s(%%Qubit*)" % s for s in
        ("h__body", "x__body", "y__body", "z__body", "s__body", "s__adj", "t__body", "t__adj")
    ) + "\ndeclare void @__quantum__qis__cnot__body(%Qubit*, %Qubit*)" \
        "\ndeclare void @__quantum__qis__cz__body(%Qubit*, %Qubit*)" \
        "\ndeclare void @__quantum__qis__swap__body(%Qubit*, %Qubit*)" \
        "\ndeclare void @__quantum__qis__mz__body(%Qubit*, %Result*)"
    skip = ("\n; gates omitidos (fuera del base profile): " + ", ".join(sorted(skipped))) if skipped else ""
    return (f"; QIR (base profile) generado por Atlas\n"
            f"%Qubit = type opaque\n%Result = type opaque\n{decls}\n\n"
            f"define void @main() #0 {{\nentry:\n" + "\n".join(body) +
            f"\n  ret void\n}}\n\n"
            f'attributes #0 = {{ "entry_point" "output_labeling_schema" "qir_profiles"="base_profile" '
            f'"required_num_qubits"="{n}" "required_num_results"="{n}" }}\n'
            f'!llvm.module.flags = !{{!0, !1}}\n'
            f'!0 = !{{i32 1, !"qir_major_version", i32 1}}\n'
            f'!1 = !{{i32 7, !"qir_minor_version", i32 0}}{skip}\n')


_QIR_BACK = {"h__body": "h", "x__body": "x", "y__body": "y", "z__body": "z", "s__body": "s",
             "s__adj": "sdg", "t__body": "t", "t__adj": "tdg", "cnot__body": "cx", "cz__body": "cz",
             "swap__body": "swap"}


def _qir_roundtrip(n, circ, qir):
    """Round-trip QIR: parsea el QIR generado de vuelta a circuito y verifica que codifica lo mismo.
    Estructural (secuencia de gates) + semántico (unitario equivalente, n<=7). Caza bugs del encoder."""
    import re
    parsed = []
    for ln in qir.splitlines():  # por línea: el ')' interno de inttoptr(...) no trunca los qubits
        m = re.search(r"call void @__quantum__qis__(\w+?)\(", ln)  # SOLO calls (no declares)
        if not m:
            continue
        name = m.group(1)
        if name == "mz__body":
            continue
        qs = [int(x) for x in re.findall(r"i64 (\d+) to %Qubit", ln)]
        g = _QIR_BACK.get(name)
        if g:
            parsed.append((g, *qs))
    src = [(g[0], *[x for x in g[1:] if isinstance(x, int)]) for g in circ if g[0] in _QIR_BACK.values()]
    structural = (parsed == src)
    out = {"structural_match": structural, "n_source_gates_in_profile": len(src), "n_qir_gates": len(parsed),
           "scope": "valida que el QIR generado codifica fielmente el circuito (encoder round-trip)"}
    if n <= 7:
        try:
            from qiskit import QuantumCircuit
            from qiskit.quantum_info import Operator
            def build(seq):
                qc = QuantumCircuit(n)
                for g in seq:
                    op = g[0]; a = g[1] if len(g) > 1 else 0; b = g[2] if len(g) > 2 else 0
                    {"h": qc.h, "x": qc.x, "y": qc.y, "z": qc.z, "s": qc.s, "sdg": qc.sdg,
                     "t": qc.t, "tdg": qc.tdg}.get(op, lambda *_: None)(a) if op in ("h","x","y","z","s","sdg","t","tdg") \
                        else {"cx": qc.cx, "cz": qc.cz, "swap": qc.swap}.get(op, lambda *_: None)(a, b)
                return qc
            out["semantic_equivalence"] = bool(Operator(build(src)).equiv(Operator(build(parsed))))
            out["semantic_scope"] = "unitario exacto (n<=7)"
        except Exception as e:
            out["semantic_equivalence"] = None; out["semantic_err"] = str(e)[:80]
    else:
        out["semantic_equivalence"] = "structural-only (n>7: unitario 2^n no práctico)"
    return out


def _qir_certificate(qasm, qir, n, roundtrip):
    """Certificado verificable (token-free, sin red) del export QIR.

    Liga el QASM de entrada, el QASM normalizado (safe_parse->to_qasm) y el QIR
    emitido via SHA-256, declara el perfil/recursos del base profile, lista ops
    fuera del gate set soportado, y resume la equivalencia semantica del
    round-trip existente (_qir_roundtrip)."""
    def _sha(s):
        return hashlib.sha256((s if isinstance(s, str) else "").encode("utf-8")).hexdigest()
    in_sha = _sha(qasm)
    norm_circ = []
    try:
        nn, cc, _w = safe_parse(qasm if isinstance(qasm, str) else "")
        norm_circ = cc
        norm_sha = _sha(to_qasm(nn, cc))
    except Exception:
        norm_sha = in_sha
    supported = set(_QIR_BACK.values()) | {"cnot"}
    unsupported = sorted({g[0] for g in norm_circ if g and g[0] not in supported})
    rt = roundtrip if isinstance(roundtrip, dict) else {}
    sem = rt.get("semantic_equivalence")
    if sem is True:
        sem_status, method, tol = "passed", "exact_unitary_equiv", 0.0
    elif sem is False:
        sem_status, method, tol = "failed", "exact_unitary_equiv", 0.0
    elif isinstance(sem, str):
        sem_status, method, tol = ("passed" if rt.get("structural_match") else "failed"), "structural_only", None
    else:
        sem_status, method, tol = "skipped", "unavailable", None
    semantic = {"status": sem_status, "method": method, "tolerance": tol,
                "structural_match": bool(rt.get("structural_match")),
                "scope": rt.get("semantic_scope") or rt.get("semantic_equivalence")}
    if rt.get("semantic_err"):
        semantic["error"] = rt["semantic_err"]
    return {
        "input_qasm_sha256": in_sha,
        "normalized_qasm_sha256": norm_sha,
        "qir_sha256": _sha(qir),
        "qir_profile": "base_profile",
        "required_num_qubits": n,
        "required_num_results": n,
        "dynamic_qubit_management": False,
        "dynamic_result_management": False,
        "unsupported_ops": unsupported,
        "semantic_equivalence": semantic,
    }


def _gen_family_meta(magic, spread, treewidth, seed):
    def dens(x):
        try:
            v = float(x)
            return max(0.0, min(1.0, v / 100.0 if v > 1 else v))
        except Exception:
            return 0.8 if x == "high" else 0.12
    m, e = dens(magic), dens(spread)
    core = max(0.08, min(1.0, 0.15 + 0.32 * e + 0.18 * m + (0.28 if m > 0.58 and e > 0.58 else 0) + (0.12 if e > 0.82 else 0)))
    if treewidth == "high":
        core = max(core, 0.72)
    family, topo = "Low-complexity request", "line / chain"
    if core >= 0.82 and m >= 0.7 and e >= 0.7:
        family, topo = "Hardness challenge request", "near-all-to-all dense interaction graph"
    elif core >= 0.68 and e >= 0.55:
        family, topo = "Dense interaction request", "dense interaction graph"
    elif core >= 0.48 and e >= 0.45:
        family, topo = "Interaction-frontier request", "hub-periphery interaction graph"
    elif e >= 0.62:
        family, topo = "Spread-heavy request", "heavy-hex-like" if e > 0.82 else "2D grid local"
    elif m >= 0.58:
        family, topo = "Magic-heavy request", "sparse random"
    return {"family_type": family, "requested_magic": round(m, 2), "requested_spread": round(e, 2),
            "requested_interaction_density": round(core, 2), "requested_core_density": round(core, 2),
            "topology": topo, "seed": seed}


def _trajectory(n, circ, steps=14):
    """MEASURED complexity climb: real diagnostics for K sampled circuit prefixes.

    Lightweight on purpose -- it computes only the route-relevant proxies
    (MPS bond, treewidth, Clifford-ness, #T), not the full cost_atlas pipeline
    (noise model, exact verification, economics).

    Efficiency: the MPS is evolved **incrementally** in a single pass, snapshotting
    the bond at the sample indices -- one O(len) MPS evolution instead of K full
    rebuilds (a ~K x saving on the usually-dominant MPS cost). Treewidth stays
    per-prefix (contraction width re-optimises the whole network each time)."""
    import numpy as np
    import quimb.tensor as qtn
    from ground_truth import treewidth_log2, stim_is_clifford
    from route_adjudicator import adjudicate_route
    L = len(circ)
    if L == 0:
        return []
    K = max(2, min(int(steps), L))
    sample = sorted({max(1, round((i + 1) * L / K)) for i in range(K)})
    sset = set(sample)

    theo_max = 1 << (n // 2)
    max_bond = min(theo_max, 1024 if n <= 20 else 64)
    cmps = qtn.CircuitMPS(n, gate_opts={"max_bond": max_bond, "cutoff": 1e-10})
    _1Q = {"h": "H", "s": "S", "t": "T", "x": "X", "y": "Y", "z": "Z", "sdg": "SDG", "tdg": "TDG"}
    mps_at = {}
    for i, g in enumerate(circ, start=1):                  # ONE incremental MPS evolution
        op = g[0]
        if op in _1Q:
            cmps.apply_gate(_1Q[op], g[1])
        elif op in ("cx", "cnot"):
            cmps.apply_gate("CX", g[1], g[2])
        elif op == "cz":
            cmps.apply_gate("CZ", g[1], g[2])
        elif op == "rz":
            cmps.apply_gate("RZ", g[2], g[1])
        if i in sset:
            b = int(cmps.psi.max_bond())
            mps_at[i] = (float(np.log2(max(1, b))), (b >= max_bond) and (max_bond < theo_max))

    pts = []
    for gi in sample:
        pref = circ[:gi]
        t_count = sum(1 for g in pref if g and g[0] == "t")
        b, trunc = mps_at[gi]
        tw, tw_exact = treewidth_log2(n, pref)
        view = {"t_count": t_count, "mps_truncated": trunc, "treewidth_exact": tw_exact, "n": n,
                "stim_clifford": stim_is_clifford(pref),
                "costs_log2": {"MPS(entangle)": round(b, 2), "contraction(treewidth)": round(tw, 2),
                               "spread(local)": None, "fold(magic)": round(0.3962 * t_count, 2)}}
        adj = adjudicate_route(view)
        pts.append({"gate_index": gi, "t_count": t_count, "mps_log2": round(b, 2),
                    "treewidth_log2": round(tw, 2), "mps_truncated": bool(trunc),
                    "route": adj["route"].lower(), "route_confidence": (adj.get("confidence") or {}).get("score")})
    return pts


_STAMP = None


def _build_stamp():
    """Build-stamp para verificación de deploy: sha256 del propio webui.py (lo que corre EN el
    contenedor) + commit SHA si se horneó en ATLAS_BUILD_SHA. El deploy.sh compara este sha contra
    el de tu webui.py local -> garantía byte-a-byte de que el live es exactamente tu código."""
    global _STAMP
    if _STAMP is None:
        import hashlib
        try:
            h = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
        except Exception:
            h = "?"
        _STAMP = {"webui_sha256": h, "build_sha": os.environ.get("ATLAS_BUILD_SHA", "?"),
                  "demo_n": 14, "backend": "ibm_kingston"}
    return _STAMP


def _frontier_json():
    """Data-driven frontier params (benchmarks/build_frontier.py). Falls back to a
    sane default if the file is absent so the UI still renders."""
    default = {"perceived_frac": 0.34, "field_frac": 0.62, "nucleo_frac": 0.9, "reclaimed_pct": None}
    try:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "benchmarks", "frontier.json")
        with open(p, encoding="utf-8") as f:
            return json.dumps(json.load(f))
    except Exception:
        return json.dumps(default)


# ---- Fase 6: chat REAL con Claude, usando el diagnostico del circuito como contexto ----
_CHAT_BASE = (
    "Eres el asistente de Atlas, una herramienta HONESTA de triage de computo cuantico (pre-flight). "
    "Marco honesto que NO debes violar: Atlas NO es nuevo poder de simulacion. La frontera clasica "
    "(tensor networks, Stim, CAMPS 2024, Qiskit Aer) es logro del CAMPO, no un hallazgo de Atlas; "
    "Sycamore RCS y la utilidad-IBM ya fueron simulados clasicamente. La orilla defendible de Atlas es el "
    "triage operacional encima: adjudicacion de ruta consciente de modos de fallo, confianza calibrada como "
    "DETECTOR DE ERRORES, y un benchmark MEDIDO no-circular (oraculo por certificados exactos: Clifford/Stim, "
    "MPS no truncado, treewidth exacto, statevector). Resultado del benchmark (736 circuitos certificados): "
    "Atlas 0.950 de acierto, 0 false-safety y 0 false-alarm; ademas guarda 50+ casos de false-safety que el "
    "MPS truncado cometeria al confiar en cotas inferiores. Rutas posibles: CPU (estabilizadores / statevector "
    "trivial), TENSOR (entrelazamiento acotado, MPS/CAMPS), HPC_FIRST (el MPS barato es una cota truncada; la "
    "contraccion gobierna), ESCALATE (statevector Y MPS Y contraccion exceden presupuesto, n>=33: nucleo QPU real). "
    "Reglas de respuesta: responde en el idioma del usuario, conciso y fundamentado SOLO en el diagnostico provisto. "
    "Distingue dureza PERCIBIDA (alto #T + entrelazamiento) de dureza MEDIDA. No sobre-afirmes ventaja cuantica ni "
    "atribuyas a Atlas poder de simulacion. Si no hay diagnostico cargado, pide al usuario que analice un circuito primero."
)


def _chat_system(diag):
    """System prompt = marco honesto + resumen compacto del diagnostico actual."""
    if not isinstance(diag, dict):
        return _CHAT_BASE + "\n\n[Sin circuito analizado en esta sesion.]"
    c = diag.get("costs_log2") or {}
    ra = diag.get("route_adjudication") or {}
    conf = ra.get("confidence") or {}
    lines = ["", "Diagnostico del circuito actualmente cargado (usa SOLO estos numeros):",
             "- n (qubits): %s" % diag.get("n"),
             "- #T (magia): %s" % diag.get("t_count"),
             "- veredicto: %s" % (diag.get("verdict") or "n/a"),
             "- ruta adjudicada: %s" % (ra.get("route") or "n/a"),
             "- estimador gobernante: %s" % (ra.get("governing_estimator") or "n/a"),
             "- score Atlas: %s/100" % diag.get("atlas_score"),
             "- confianza: %s (%s)" % (conf.get("label") or "n/a", conf.get("score")),
             "- MPS(entangle) log2: %s" % c.get("MPS(entangle)"),
             "- spread(local) log2: %s" % c.get("spread(local)"),
             "- contraction(treewidth) log2: %s" % c.get("contraction(treewidth)")]
    if diag.get("entanglement_entropy") is not None:
        lines.append("- entropia de entrelazamiento (nats): %s" % diag.get("entanglement_entropy"))
    if diag.get("mps_truncated"):
        lines.append("- AVISO: el MPS esta TRUNCADO -> su coste es una COTA INFERIOR, no una garantia.")
    return _CHAT_BASE + "\n".join(lines)


def _chat_reply(messages, diag):
    """Una vuelta de chat contra Claude (no streaming; max_tokens acotado para latencia)."""
    client = _anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        thinking={"type": "adaptive"},           # razonamiento adaptativo (recomendado)
        system=_chat_system(diag),
        messages=messages,
    )
    if getattr(resp, "stop_reason", None) == "refusal":
        return "(Claude declino responder esta peticion.)"
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text" and getattr(b, "text", "")]
    return ("\n".join(parts)).strip() or "(sin respuesta)"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        # vendored static assets (offline-safe: Three.js served locally, no CDN)
        if self.path.startswith("/vendor/"):
            rel = self.path.split("?", 1)[0].lstrip("/").replace("..", "")
            fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)
            _CT = {".js": "application/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                   ".html": "text/html; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}
            _ext = os.path.splitext(fp)[1]
            if os.path.isfile(fp) and _ext in _CT:
                with open(fp, "rb") as fh:
                    body = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", _CT[_ext])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers(); self.wfile.write(body); return
            self._send(404, json.dumps({"error": "asset no encontrado"})); return
        if self.path in ("/v2", "/v2/"):   # rediseño UX v2 (mockup estático) — v1 sigue en "/"
            v2p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "v2", "index.html")
            try:
                with open(v2p, "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8"); return
            except Exception:
                self._send(404, json.dumps({"error": "v2 no disponible"})); return
        if self.path == "/api/version":   # build-stamp: el deploy.sh compara live vs local byte-a-byte
            self._send(200, json.dumps(_build_stamp())); return
        page = PAGE.replace("%DEMO%", _demo_qasm(14, 5).replace("\n", "\\n")).replace("%FRONTIER%", _frontier_json())  # n=14 = frontera exacta (ARSENAL_CAP): máximo n con arsenal completo (spread/MPS/treewidth/statevector EXACTOS, 21ms) — impresiona sin caveats ni pérdida
        self._send(200, page, "text/html; charset=utf-8")

    def do_POST(self):
        try:
            # P1-5 DoS guard: hard cap the request body BEFORE reading it.
            clen = int(self.headers.get("Content-Length") or 0)
            if clen > 2_000_000:                              # 2 MB cap on any request body
                self._send(200, json.dumps({"error": "peticion demasiado grande (>2 MB)"})); return
            try:
                data = json.loads(self.rfile.read(clen) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self._send(200, json.dumps({"error": "JSON invalido en la peticion"})); return
            if not isinstance(data, dict):
                self._send(200, json.dumps({"error": "el cuerpo debe ser un objeto JSON"})); return
            # P1-5: hard cap the QASM string length for every endpoint that takes one.
            _q = data.get("qasm")
            if isinstance(_q, str) and len(_q) > 500_000:     # ~500 KB QASM ceiling
                self._send(200, json.dumps({"error": "QASM demasiado grande (>500 KB); usa la CLI atlas.py"})); return
            if self.path == "/api/chat":                      # Fase 6: chat REAL con Claude (diagnostico como contexto)
                if _anthropic is None:
                    self._send(200, json.dumps({"error": "Chat externo deshabilitado en este deployment (por privacidad: no se envían datos a un LLM externo). El triage de Atlas funciona completo sin él. Para habilitarlo en local: pip install anthropic + ANTHROPIC_API_KEY.", "fallback": True})); return
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    self._send(200, json.dumps({"error": "Chat no disponible: define ANTHROPIC_API_KEY en el entorno para conectar Claude.", "fallback": True})); return
                raw = data.get("messages")
                if not isinstance(raw, list) or not raw:
                    self._send(200, json.dumps({"error": "el campo 'messages' debe ser una lista no vacia"})); return
                msgs = []
                for m in raw[-20:]:                            # ultimos 20 turnos, saneados
                    if not isinstance(m, dict):
                        continue
                    role, content = m.get("role"), m.get("content")
                    if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                        msgs.append({"role": role, "content": content[:8000]})
                while msgs and msgs[0]["role"] != "user":      # la conversacion debe empezar en 'user'
                    msgs.pop(0)
                if not msgs:
                    self._send(200, json.dumps({"error": "no hay mensajes de usuario validos"})); return
                diag = data.get("diagnostics") if isinstance(data.get("diagnostics"), dict) else None
                try:
                    self._send(200, json.dumps({"reply": _chat_reply(msgs, diag)}))
                except Exception as e:
                    self._send(200, json.dumps({"error": "error consultando Claude: " + str(e)[:200]}))
                return
            if self.path == "/api/qir":                       # export a QIR (LLVM IR, base profile)
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str) or not qasm.strip():
                    self._send(200, json.dumps({"error": "el campo 'qasm' debe ser texto OpenQASM"})); return
                n, circ, warns = safe_parse(qasm)
                qir = _to_qir(n, circ)
                rt = _qir_roundtrip(n, circ, qir)
                cert = _qir_certificate(qasm, qir, n, rt)
                self._send(200, json.dumps({"qir": qir, "n": n, "roundtrip": rt, "certificate": cert})); return
            if self.path == "/api/diagnose":
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str):                 # Bug IV: sin .strip() sobre no-strings, error limpio
                    self._send(200, json.dumps({"error": "el campo 'qasm' debe ser texto OpenQASM"})); return
                n, circ, warns = safe_parse(qasm)
                if data.get("full_circuit"):                  # "Ver todos": render SIN truncar y SIN re-analizar
                    self._send(200, json.dumps({"n": n, "circuit": _render_gates(circ, n, cap=len(circ))})); return
                # red-team (benchmarks/adversarial_attack.py): el triage in-process (quimb/cotengra) se CUELGA
                # en C con circuitos profundos (>~300 gates) o de LARGO ALCANCE (cotengra explota aunque haya
                # pocas gates: longrange n=20 380g = 30s). signal.alarm no interrumpe C, y el guard de
                # multiprocessing FORK se deadlockea desde un hilo del server dentro del contenedor (CPython
                # fork+threads: el hijo hereda locks bloqueados, issue27422/cpython#96971). Discriminador
                # barato: alcance máximo de las 2q. Lo potencialmente lento -> subproceso KILLABLE (cold-start
                # ~3.5s) con timeout real -> nunca cuelga el server. Lo chico-local queda in-process (instantáneo).
                _2q = [g for g in circ if len(g) >= 3 and isinstance(g[1], int) and isinstance(g[2], int)]
                _reach = max((abs(g[1] - g[2]) for g in _2q), default=0)
                if n > 60 or len(circ) > 300 or _reach > 6:
                    import subprocess
                    runner = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atlas_run.py")
                    try:
                        pr = subprocess.run([sys.executable, runner], input=qasm.encode(),
                                            capture_output=True,
                                            timeout=float(data.get("timeout_s", int(os.environ.get("ATLAS_TIMEOUT_S", "30")))))
                        out = json.loads(pr.stdout.decode() or "{}")
                        out.setdefault("n", n); out["delegated_to_cli"] = True
                        out["circuit"] = _render_gates(circ, n)
                        self._send(200, json.dumps(out)); return
                    except subprocess.TimeoutExpired:
                        self._send(200, json.dumps({"n": n, "compute_bound": True,
                            "delegated_to_cli": True,
                            "verdict": f"COMPUTE-BOUND: n={n} excedio el presupuesto local (CLI). "
                                       "Defiere a HPC o aumenta timeout_s.",
                            "route_adjudication": {"route": "HPC_FIRST", "governing_estimator": "compute-bound",
                                "governing_reason": "local CLI exceeded wall-clock budget",
                                "confidence": {"label": "low", "score": 0}}})); return
                    except Exception as e:
                        self._send(200, json.dumps({"error": f"delegacion CLI fallo: {str(e)[:160]}"})); return
                # In-process es seguro aquí: los circuitos potencialmente lentos (n>60 o >500 gates)
                # ya se delegaron al subproceso killable arriba. Lo que llega aquí es chico -> triage rápido.
                r = cost_atlas(n, circ); r["warnings"] = warns
                # spread_state explícito (P4 audit): no mezclar 'n/a' que significa cosas distintas
                _sp = (r.get("costs_log2") or {}).get("spread(local)")
                _gov = ((r.get("route_adjudication") or {}).get("governing_estimator") or "").lower()
                r["spread_state"] = ("computed_governing" if (_sp is not None and "spread" in _gov)
                                     else "computed_not_governing" if _sp is not None
                                     else "not_applicable_n_gt_14" if n > 14
                                     else "skipped_fast_path" if r.get("fast_path")
                                     else "not_used_this_circuit")
                r["n"] = n; r["circuit"] = _render_gates(circ, n); r["qasm_in"] = to_qasm(n, circ)
                if _phys is not None:                          # F-1: OBSERVABLE FISICO (no de coste)
                    ent, skip = _phys.circuit_entropy(n, circ)
                    r["entanglement_entropy"] = ent            # entropia von Neumann en nats (None si n>14)
                    r["entanglement_skipped"] = skip
                    try:                                       # anti S-spoofing: S en TODOS los cortes, no solo n/2
                        prof, pskip = _phys.entanglement_profile(n, circ)
                        if prof is not None:
                            r["entanglement_profile"] = prof   # {s_half,s_max,argmax_cut,asymmetry,profile}
                    except Exception:
                        pass
                    r["phys_selftest"] = _PHYS_SELFTEST        # Bell=ln2 etc. verificado contra analitico
                    r["magic_check"] = _phys.magic_cross_check(n, circ, r.get("t_count"))  # magia del ESTADO vs T-count
                try:
                    from economics import economics as _econ
                    v = r.get("verdict", ""); trac = "TRACTABLE" in v and "INTRACTABLE" not in v
                    r["econ"] = _econ(n, circ, trac, treewidth_log2=r["costs_log2"]["contraction(treewidth)"])
                except Exception as e:
                    r["econ"] = None; r["econ_err"] = str(e)
                if _certificate is not None:                  # capa de producto: certificado honesto
                    try:
                        r["certificate"] = _certificate(r.get("qasm_in") or qasm)
                    except Exception as e:
                        r["certificate"] = None; r["certificate_err"] = str(e)[:200]
                self._send(200, json.dumps(r)); return
            if self.path == "/api/certificate":               # certificado honesto solo (witness+conformal+driver+impossibility)
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str):
                    self._send(200, json.dumps({"error": "el campo 'qasm' debe ser texto OpenQASM"})); return
                if _certificate is None:
                    self._send(200, json.dumps({"error": "atlas_certificate no disponible en el server"})); return
                self._send(200, json.dumps(_certificate(qasm))); return
            if self.path == "/api/harden":                    # explorar complejidad: donde cruza CPU->TENSOR->HPC->ESCALATE
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str):
                    self._send(200, json.dumps({"error": "el campo 'qasm' debe ser texto OpenQASM"})); return
                if _harden is None:
                    self._send(200, json.dumps({"error": "boundary_sweep no disponible en el server"})); return
                nmax = min(int(data.get("n_max", 26) or 26), 32)   # acota el barrido (cada n usa guard 8s)
                if data.get("async"):                              # ASYNC: arranca en thread, devuelve job_id; el cliente hace poll
                    with _HARDEN_LOCK:
                        _HARDEN_SEQ[0] += 1; jid = "h%d" % _HARDEN_SEQ[0]
                        _HARDEN_JOBS[jid] = {"status": "running"}
                    def _run(jid=jid, qasm=qasm, nmax=nmax):
                        try:
                            res = _harden(qasm, n_max=nmax, step=9); _HARDEN_JOBS[jid] = {"status": "done", "result": res}
                        except Exception as e:
                            _HARDEN_JOBS[jid] = {"status": "error", "error": str(e)[:200]}
                    threading.Thread(target=_run, daemon=True).start()
                    self._send(200, json.dumps({"job_id": jid, "status": "running"})); return
                self._send(200, json.dumps(_harden(qasm, n_max=nmax, step=9))); return
            if self.path == "/api/harden_status":              # poll del job async de harden
                jid = data.get("job_id", "")
                j = _HARDEN_JOBS.get(jid)
                if j is None:
                    self._send(200, json.dumps({"error": "job_id desconocido"})); return
                if j.get("status") == "done":                   # entregar y limpiar
                    _HARDEN_JOBS.pop(jid, None); self._send(200, json.dumps({"status": "done", **j["result"]})); return
                self._send(200, json.dumps(j)); return
            if self.path == "/api/benchmark":                 # bundle de benchmark auditable
                if _bench_bundle is None:
                    self._send(200, json.dumps({"error": "atlas_benchmark_bundle no disponible"})); return
                self._send(200, json.dumps(_bench_bundle())); return
            if self.path == "/api/hardware":                  # realidad hardware ibm_kingston (snapshot ESTATICO, sin token)
                try:
                    from atlas_hardware import KINGSTON_SNAPSHOT, calibration_freshness
                    _hw = dict(KINGSTON_SNAPSHOT)
                    _hw["calibration_freshness"] = calibration_freshness()  # fecha medida + warning rancio (sin reloj/red)
                    self._send(200, json.dumps(_hw)); return
                except Exception as e:
                    self._send(200, json.dumps({"error": "snapshot no disponible: " + str(e)[:160]})); return
            if self.path == "/api/emulate":                   # C-lite: emulador ruidoso TOKEN-FREE (tabla horneada)
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str) or not qasm.strip():
                    self._send(200, json.dumps({"error": "pega un circuito OpenQASM"})); return
                try:
                    from atlas_hardware import emulate_lite
                    self._send(200, json.dumps(emulate_lite(qasm))); return
                except Exception as e:
                    self._send(200, json.dumps({"error": "emulate: " + str(e)[:160]})); return
            if self.path == "/api/compute":                   # el '+': entrega el resultado SOLO si el triage lo certificó barato
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str) or not qasm.strip():
                    self._send(200, json.dumps({"error": "pega un circuito OpenQASM"})); return
                try:
                    from ground_truth import compute_result
                    n, circ, _ = safe_parse(qasm)
                    r = cost_atlas(n, circ)
                    route = (r.get("route_adjudication") or {}).get("route")
                    out = compute_result(n, circ, r.get("t_count", 0), qasm=qasm, route=route,
                                         mps_truncated=bool(r.get("mps_truncated")))
                    self._send(200, json.dumps(out)); return
                except Exception as e:
                    self._send(200, json.dumps({"error": "compute: " + str(e)[:160]})); return
            if self.path == "/api/reachability":              # mirror-RB: reachability a cualquier n SIN statevector
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str) or not qasm.strip():
                    self._send(200, json.dumps({"error": "pega un circuito OpenQASM"})); return
                try:
                    from atlas_hardware import reachability
                    n, circ, _ = safe_parse(qasm)
                    self._send(200, json.dumps(reachability(n, circ))); return
                except Exception as e:
                    self._send(200, json.dumps({"error": "reachability: " + str(e)[:160]})); return
            if self.path == "/api/embedding":                 # B: embedding óptimo token-free (tabla horneada)
                try:
                    from atlas_hardware import recommend_embedding_offline
                    nq = int(data.get("n_qubits") or (safe_parse(data.get("qasm", ""))[0] if data.get("qasm") else 8))
                    self._send(200, json.dumps(recommend_embedding_offline(nq))); return
                except Exception as e:
                    self._send(200, json.dumps({"error": "embedding: " + str(e)[:160]})); return
            if self.path == "/api/segment":                   # triage hibrido por segmento
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str):
                    self._send(200, json.dumps({"error": "el campo 'qasm' debe ser texto OpenQASM"})); return
                if _segment is None:
                    self._send(200, json.dumps({"error": "atlas_segment no disponible"})); return
                ns = min(int(data.get("n_segments", 3) or 3), 8)
                self._send(200, json.dumps(_segment(qasm, n_segments=ns))); return
            if self.path == "/api/gpu":                       # ruta GPU statevector (frontera dinamica)
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str):
                    self._send(200, json.dumps({"error": "el campo 'qasm' debe ser texto OpenQASM"})); return
                if _gpu_advice is None:
                    self._send(200, json.dumps({"error": "atlas_gpu_route no disponible"})); return
                n, circ, _w = safe_parse(qasm)
                r = cost_atlas(n, circ); ra = r.get("route_adjudication") or {}
                self._send(200, json.dumps(_gpu_advice(n, ra.get("route"), r.get("costs_log2") or {}))); return
            if self.path == "/api/variational":               # triage VQE/QAOA (caso QPU real)
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str):
                    self._send(200, json.dumps({"error": "el campo 'qasm' debe ser texto OpenQASM"})); return
                if _variational is None:
                    self._send(200, json.dumps({"error": "atlas_variational no disponible"})); return
                npar = int(data.get("n_params", 8) or 8); nit = int(data.get("n_iters", 100) or 100)
                self._send(200, json.dumps(_variational(qasm, n_params=npar, n_iters=nit))); return
            if self.path == "/api/trajectory":                # climb MEDIDO: diagnosticos reales por prefijo
                qasm = data.get("qasm", "")
                if not isinstance(qasm, str) or not qasm.strip():
                    self._send(200, json.dumps({"error": "el campo 'qasm' debe ser texto OpenQASM"})); return
                n, circ, warns = safe_parse(qasm)
                if n > 30:
                    self._send(200, json.dumps({"error": f"n={n}>30: trayectoria medida limitada a n<=30", "n": n})); return
                try:
                    steps = max(2, min(24, int(data.get("steps", 14))))
                except (TypeError, ValueError):
                    steps = 14
                self._send(200, json.dumps({"n": n, "trajectory": _trajectory(n, circ, steps)})); return
            if self.path == "/api/generate":
                n = validate_n(data.get("n", 12), cap=60)
                try: _seed = int(data.get("seed", 0))                  # FE-3: seed variable -> el dado 🎲 varia
                except (TypeError, ValueError): _seed = 0              # el circuito; mismo seed => reproducible
                magic_req, spread_req, tw_req = data.get("magic", "low"), data.get("spread", "low"), data.get("treewidth", "low")
                native = build_target(n, 6, magic_req, spread_req, data.get("book", "core"), tw_req, seed=_seed)
                dec = decompose(native)                                   # hop -> {h,rz,cx}
                qasm = to_qasm(n, dec)
                n, circ, warns = safe_parse(qasm)                         # normaliza rz->t (gate set del motor):
                r = cost_atlas(n, circ)                                    # arregla el KeyError 'rz'/'hop' del arsenal
                r["libro_flattener"] = which_flattener(native)
                r["t_count"] = sum(1 for g in circ if g and g[0] == "t")
                r["qasm"] = qasm; r["qasm_in"] = qasm; r["warnings"] = warns
                r["family_meta"] = _gen_family_meta(magic_req, spread_req, tw_req, _seed)
                r["n"] = n; r["circuit"] = _render_gates(circ, n)         # para el diagrama, sin re-analizar
                try:
                    from economics import economics as _econ
                    v = r.get("verdict", ""); trac = "TRACTABLE" in v and "INTRACTABLE" not in v
                    r["econ"] = _econ(n, circ, trac, treewidth_log2=r["costs_log2"]["contraction(treewidth)"])
                except Exception:
                    r["econ"] = None
                self._send(200, json.dumps(r)); return
            self._send(404, json.dumps({"error": "no encontrado"}))
        except ValueError as e:
            self._send(200, json.dumps({"error": str(e)}))                    # error de dominio: mensaje limpio
        except Exception:
            self._send(200, json.dumps({"error": "error interno procesando la peticion"}))   # sin filtrar traceback


def _warmup():
    """Calienta imports/cotengra/estimadores con 1 análisis en un thread daemon al boot, para que
    el PRIMER request real (incl. el demo en window.onload) no pague los ~10s de cold-start. Azure
    escala a cero -> sin esto el primer visitante tras idle sufre el warmup. (sin pérdida de optimización.)"""
    try:
        n, circ, _ = safe_parse(_demo_qasm(8, 4))
        cost_atlas(n, circ)
    except Exception:
        pass


def main():
    assert _verify_hop(), "descomposicion hop incorrecta"
    import threading as _th
    _th.Thread(target=_warmup, daemon=True).start()   # warm-up no-bloqueante: el server acepta requests ya
    print(f"Atlas IDE en  ->  http://localhost:{PORT}   (Ctrl-C para parar)")
    ThreadingHTTPServer((HOST, PORT), H).serve_forever()   # multi-thread: peticiones concurrentes no se bloquean


if __name__ == "__main__":
    main()

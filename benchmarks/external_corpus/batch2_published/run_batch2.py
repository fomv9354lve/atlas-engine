"""OFFLINE research harness (batch 2): expand Atlas's EXTERNAL-validation corpus
with MORE real, published circuits and run them through the REAL engine
(cost_atlas + route_adjudicator from HANDOFF_5ideas/).

Sources (all genuinely external / community-standard, NOT self-generated):
  - QASMBench  (Li et al., ACM TQC 2023; github.com/pnnl/QASMBench)
  - MQT Bench  (Quetschlich, Burgholzer, Wille, Quantum 7, 1062 (2023);
                github.com/cda-tum/mqt-bench), algorithm (ALG) level.

We deliberately SKIP the QASMBench circuits already in batch 1
(adder_n28, bv_n70, cat_n65, dnn_n33, ghz_n127, ising_n34/66, knn_n31,
 multiplier_n45, qft_n29/63, qugan_n39, QV_n32, vqe_uccsd_n28) and take the
OTHERS, across families and sizes.

Per circuit: parse with Atlas safe_parse, run REAL cost_atlas, read the REAL
route_adjudicator route. Each circuit runs in its own subprocess with a
~600 s wall cap; on timeout we record route="TIMEOUT" honestly and move on.

Data only: writes ONLY under this batch2_published/ dir. No deploy, no git, no
site edits. The live web n-cap is untouched (we call cost_atlas directly here).
"""
from __future__ import annotations
import os, sys, json, glob, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
QDIR = os.path.join(HERE, "qasm")
WORKER = os.path.join(os.path.dirname(HERE), "worker.py")  # reuse batch1 worker (read-only)
VENV_PY = "/Users/kreniq/Desktop/KRENIQ/AI Projects/01. Investigacion/00. OPORTUNIDADES/codex_subrepo/atlas-codex/.atlas-venv/bin/python"
QB = "/private/tmp/claude-501/-Users-kreniq-Desktop-KRENIQ-AI-Projects-01--Investigacion-physics-magnitude-lab/59534d24-537e-46a5-b569-4e533c23aad5/scratchpad/QASMBench"
TIMEOUT_S = 300  # per-circuit wall cap; exceeding -> route="TIMEOUT" (honest). Cap reported.
RESULTS_PATH = os.path.join(HERE, "results.json")
os.makedirs(QDIR, exist_ok=True)

QB_CITE = "QASMBench (Li, Stein, Krishnamoorthy, Ang, ACM TQC 2023); github.com/pnnl/QASMBench"
MQT_CITE = "MQT Bench (Quetschlich, Burgholzer, Wille, Quantum 7, 1062 (2023)); github.com/cda-tum/mqt-bench"

# (display_name, category, dirname) -- selection NOT in batch1.
QASMBENCH = [
    # --- small ---
    ("adder_n10",        "small", "adder_n10"),
    ("hhl_n10",          "small", "hhl_n10"),
    ("ising_n10",        "small", "ising_n10"),
    ("qpe_n9",           "small", "qpe_n9"),
    ("sat_n7",           "small", "sat_n7"),
    ("shor_n5",          "small", "shor_n5"),
    ("simon_n6",         "small", "simon_n6"),
    ("vqe_uccsd_n8",     "small", "vqe_uccsd_n8"),
    # --- medium ---
    ("bigadder_n18",     "medium", "bigadder_n18"),
    ("bv_n19",           "medium", "bv_n19"),
    ("bwt_n21",          "medium", "bwt_n21"),
    ("cat_state_n22",    "medium", "cat_state_n22"),
    ("cc_n12",           "medium", "cc_n12"),
    ("dnn_n16",          "medium", "dnn_n16"),
    ("factor247_n15",    "medium", "factor247_n15"),
    ("ghz_state_n23",    "medium", "ghz_state_n23"),
    ("hhl_n14",          "medium", "hhl_n14"),
    ("ising_n26",        "medium", "ising_n26"),
    ("knn_n25",          "medium", "knn_n25"),
    ("multiplier_n15",   "medium", "multiplier_n15"),
    ("qft_n18",          "medium", "qft_n18"),
    ("qram_n20",         "medium", "qram_n20"),
    ("sat_n11",          "medium", "sat_n11"),
    ("square_root_n18",  "medium", "square_root_n18"),
    ("swap_test_n25",    "medium", "swap_test_n25"),
    ("vqe_n24",          "medium", "vqe_n24"),
    ("wstate_n27",       "medium", "wstate_n27"),
    # --- large ---
    ("QV_n100",          "large", "QV_n100"),
    ("adder_n64",        "large", "adder_n64"),
    ("bv_n30",           "large", "bv_n30"),
    ("bwt_n37",          "large", "bwt_n37"),
    ("cat_n35",          "large", "cat_n35"),
    ("cc_n32",           "large", "cc_n32"),
    ("dnn_n51",          "large", "dnn_n51"),
    ("ghz_n40",          "large", "ghz_n40"),
    ("ising_n42",        "large", "ising_n42"),
    ("knn_n41",          "large", "knn_n41"),
    ("multiplier_n75",   "large", "multiplier_n75"),
    ("qft_n160",         "large", "qft_n160"),
    ("qugan_n71",        "large", "qugan_n71"),
    ("square_root_n45",  "large", "square_root_n45"),
    ("swap_test_n41",    "large", "swap_test_n41"),
    ("wstate_n76",       "large", "wstate_n76"),
]

CLASSICAL_TIERS = {"CPU", "TENSOR", "HPC_FIRST"}


def find_qasm(dirpath):
    cands = sorted(glob.glob(os.path.join(dirpath, "*.qasm")) +
                   glob.glob(os.path.join(dirpath, "*.qasm3")))
    cands = [c for c in cands if "transpiled" not in os.path.basename(c)
             and not os.path.basename(c).startswith("qubit_indices")]
    return cands[0] if cands else None


def stage():
    """Return list of (name, abs_qasm_path, source_str, suite)."""
    out = []
    # QASMBench (copy real .qasm into our qasm/ dir)
    for name, cat, dirn in QASMBENCH:
        src = find_qasm(os.path.join(QB, cat, dirn))
        if not src:
            print(f"  MISSING in QASMBench repo: {name} ({cat}/{dirn})", file=sys.stderr)
            continue
        ext = os.path.splitext(src)[1]
        dst = os.path.join(QDIR, f"qb_{name}{ext}")
        shutil.copyfile(src, dst)
        out.append((f"qb_{name}", dst,
                    f"{QB_CITE}; {cat}/{dirn}/{os.path.basename(src)}", "QASMBench"))
    # MQT Bench (already generated by gen_mqt.py into qasm/mqt_*.qasm)
    man_path = os.path.join(HERE, "mqt_manifest.json")
    if os.path.exists(man_path):
        for m in json.load(open(man_path)):
            if not m.get("ok"):
                continue
            out.append((m["tag"], m["file"],
                        f"{MQT_CITE}; benchmark='{m['bench']}' (algorithm level), n={m['n']}",
                        "MQT Bench"))
    return out


def write_results(results):
    routes = ["CPU", "TENSOR", "HPC_FIRST", "ESCALATE", "TIMEOUT"]
    dist = {r: sum(1 for x in results if x.get("route") == r) for r in routes}
    errors = [x["name"] for x in results if x.get("status") == "ERROR"]
    by_suite = {}
    for x in results:
        by_suite[x["suite"]] = by_suite.get(x["suite"], 0) + 1
    summary = {
        "total_new_circuits": len(results),
        "by_suite": by_suite,
        "route_distribution": dist,
        "errors": errors,
        "n_errors": len(errors),
        "per_circuit_timeout_s": TIMEOUT_S,
    }
    payload = {"summary": summary, "results": results,
               "engine": "atlas-codex/HANDOFF_5ideas cost_atlas + route_adjudicator (REAL)",
               "sources": [QB_CITE, MQT_CITE],
               "note": "Offline research harness (batch 2). Web n-cap bypassed "
                       "(cost_atlas called directly); live cap untouched; nothing deployed."}
    tmp = RESULTS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, RESULTS_PATH)
    return summary


def run_one(name, path):
    try:
        p = subprocess.run([VENV_PY, WORKER, path],
                           capture_output=True, text=True, timeout=TIMEOUT_S)
        if p.returncode != 0:
            return {"status": "ERROR",
                    "error": (p.stderr.strip().splitlines() or ["?"])[-1][:300]}
        rec = json.loads(p.stdout.strip().splitlines()[-1])
        rec["status"] = "ok"
        return rec
    except subprocess.TimeoutExpired:
        return {"status": "ok", "route": "TIMEOUT", "timeout_s": TIMEOUT_S,
                "governing_estimator": None}
    except Exception as e:
        return {"status": "ERROR", "error": f"{type(e).__name__}: {e}"}


def main():
    circuits = stage()
    print(f"staged {len(circuits)} circuits", flush=True)

    # Resume: load any already-computed results and skip those names.
    results = []
    done = set()
    if os.path.exists(RESULTS_PATH):
        try:
            prev = json.load(open(RESULTS_PATH))
            results = prev.get("results", [])
            done = {r["name"] for r in results}
            print(f"resuming: {len(done)} circuits already done", flush=True)
        except Exception:
            results, done = [], set()

    todo = [c for c in circuits if c[0] not in done]
    print(f"{len(todo)} circuits remaining\n", flush=True)

    for name, path, source, suite in todo:
        print(f"running {name} ...", flush=True)
        rec = run_one(name, path)
        rec["name"] = name
        rec["source"] = source
        rec["suite"] = suite
        route = rec.get("route")
        rec["classical_tier"] = route in CLASSICAL_TIERS
        results.append(rec)
        print(f"   -> {rec.get('status')} route={route} "
              f"gov={rec.get('governing_estimator')} "
              f"tw=2^{rec.get('treewidth_log2')} mps=2^{rec.get('mps_bond_log2')} "
              f"T={rec.get('t_count')} n={rec.get('n')} ({rec.get('elapsed_s')}s)",
              flush=True)
        write_results(results)  # checkpoint after EVERY circuit

    summary = write_results(results)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()

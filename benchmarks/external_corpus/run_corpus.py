"""OFFLINE research harness: run Atlas's REAL engine (cost_atlas + route_adjudicator)
on circuits the FIELD published as hard / QPU-requiring, and record the actual
routes. Honest thesis test: do circuits assumed to need a QPU route to a
CLASSICAL tier (CPU/TENSOR/HPC), not blind ESCALATE? This is NOT "laptop beats
QPU" -- several were classically reproduced only via large HPC / tensor-network
runs. Routing them to HPC/TENSOR is the correct, citable outcome.

Does NOT deploy anything and adds no claim to the live site.
"""
from __future__ import annotations
import os, sys, json, subprocess, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
QASM_DIR = os.path.join(HERE, "qasm")
QB = "/private/tmp/claude-501/-Users-kreniq-Desktop-KRENIQ-AI-Projects-01--Investigacion-physics-magnitude-lab/59534d24-537e-46a5-b569-4e533c23aad5/scratchpad/QASMBench"
VENV_PY = ".atlas-venv/bin/python"
TIMEOUT_S = 600

os.makedirs(QASM_DIR, exist_ok=True)


def gen_kicked_ising():
    """Priority-1 circuit: Kim et al. 127q kicked-Ising. Emit a couple of depths."""
    sys.path.insert(0, HERE)
    from heavy_hex import kicked_ising_qasm
    import math
    out = []
    for steps in (5, 20):
        fn = os.path.join(QASM_DIR, f"kicked_ising_127q_{steps}steps.qasm")
        with open(fn, "w") as f:
            f.write(kicked_ising_qasm(n_steps=steps, theta_J=-math.pi / 2, phi=math.pi / 2))
        out.append((f"kicked_ising_127q_{steps}steps", fn))
    return out


# QASMBench selections: (display_name, repo_relative_path)
QASMBENCH = [
    ("QV_n32",          "large/QV_n32/32.qasm"),
    ("qft_n29",         "large/qft_n29/qft_n29.qasm"),
    ("qft_n63",         "large/qft_n63/qft_n63.qasm"),
    ("ising_n34",       "large/ising_n34/ising_n34.qasm"),
    ("ising_n66",       "large/ising_n66/ising_n66.qasm"),
    ("adder_n28",       "large/adder_n28/adder_n28.qasm"),
    ("multiplier_n45",  "large/multiplier_n45/multiplier_n45.qasm"),
    ("ghz_n127",        "large/ghz_n127/ghz_n127.qasm"),
    ("cat_n65",         "large/cat_n65/cat_n65.qasm"),
    ("bv_n70",          "large/bv_n70/bv_n70.qasm"),
    ("vqe_uccsd_n28",   "large/vqe_uccsd_n28/vqe_uccsd_n28.qasm"),
    ("qugan_n39",       "large/qugan_n39/qugan_n39.qasm"),
    ("knn_n31",         "large/knn_n31/knn_n31.qasm"),
    ("dnn_n33",         "large/dnn_n33/dnn_n33.qasm"),
]

# Per-circuit provenance + honest field-claim framing.
META = {
    "kicked_ising_127q_5steps": dict(
        source="Kim et al., Nature 618, 500 (2023), 'Evidence for the utility of quantum computing before fault tolerance' (127q Eagle, kicked transverse-field Ising)",
        field_claim="QPU 'utility'-beyond-brute-force-classical; flagship field-assumed-hard case",
        classically_by="Tindall, Fishman, Stoudenmire, Sels, PRX Quantum 5, 020332 (2024) (tensor networks); also Begusic & Chan (2024), Liao et al. (2023), Patra et al. (2024)",
        kind="field-assumed-QPU"),
    "kicked_ising_127q_20steps": dict(
        source="Kim et al., Nature 618, 500 (2023) (127q Eagle, kicked TFIM; deeper Floquet regime)",
        field_claim="QPU 'utility'-beyond-brute-force-classical; deeper-step regime",
        classically_by="Tindall et al., PRX Quantum 5, 020332 (2024) and follow-ups (tensor networks)",
        kind="field-assumed-QPU"),
    "QV_n32": dict(
        source="QASMBench (Li et al., ACM TQC 2023); Quantum Volume protocol, Cross et al., PRA 100, 032328 (2019)",
        field_claim="QV is an intentionally hard random-SU(4) benchmark (worst-case-ish, high treewidth by design)",
        classically_by="random QV at n=32 is within reach of statevector/TN classical sim (2^32 ~ 64 GB SV; TN cheaper)",
        kind="hard-labeled-benchmark"),
    "qft_n29": dict(source="QASMBench (Li et al. 2023); Quantum Fourier Transform",
        field_claim="large/hard-labeled benchmark", classically_by="QFT has low treewidth (TN-easy); routine classical sim", kind="hard-labeled-benchmark"),
    "qft_n63": dict(source="QASMBench (Li et al. 2023); Quantum Fourier Transform, 63q",
        field_claim="large/hard-labeled benchmark (n>statevector ceiling)", classically_by="QFT low treewidth; TN-tractable", kind="hard-labeled-benchmark"),
    "ising_n34": dict(source="QASMBench (Li et al. 2023); Ising-model dynamics",
        field_claim="physics-dynamics benchmark", classically_by="1D/low-entanglement Ising is TN/MPS-tractable", kind="hard-labeled-benchmark"),
    "ising_n66": dict(source="QASMBench (Li et al. 2023); Ising-model dynamics, 66q",
        field_claim="physics-dynamics benchmark (n>statevector ceiling)", classically_by="low-entanglement Ising is TN/MPS-tractable", kind="hard-labeled-benchmark"),
    "adder_n28": dict(source="QASMBench (Li et al. 2023); reversible ripple-carry adder",
        field_claim="arithmetic benchmark (T-heavy)", classically_by="reversible arithmetic = low treewidth; Clifford+T TN-tractable", kind="hard-labeled-benchmark"),
    "multiplier_n45": dict(source="QASMBench (Li et al. 2023); reversible multiplier, 45q",
        field_claim="arithmetic benchmark (very T-heavy, n>SV ceiling)", classically_by="reversible arithmetic = low treewidth despite high T", kind="hard-labeled-benchmark"),
    "ghz_n127": dict(source="QASMBench (Li et al. 2023); 127q GHZ state",
        field_claim="large-n entangled-state benchmark", classically_by="pure Clifford -> Stim poly-time for any n (Aaronson-Gottesman 2004)", kind="hard-labeled-benchmark"),
    "cat_n65": dict(source="QASMBench (Li et al. 2023); 65q cat state",
        field_claim="large-n entangled-state benchmark", classically_by="pure Clifford -> Stim poly-time", kind="hard-labeled-benchmark"),
    "bv_n70": dict(source="QASMBench (Li et al. 2023); Bernstein-Vazirani, 70q",
        field_claim="algorithmic benchmark", classically_by="Clifford-dominated -> Stim/low-treewidth tractable", kind="hard-labeled-benchmark"),
    "vqe_uccsd_n28": dict(source="QASMBench (Li et al. 2023); VQE UCCSD chemistry ansatz, 28q",
        field_claim="chemistry-ansatz benchmark", classically_by="statevector at n=28 (~4 GB) is classically feasible", kind="hard-labeled-benchmark"),
    "qugan_n39": dict(source="QASMBench (Li et al. 2023); quantum GAN, 39q",
        field_claim="QML benchmark (n>SV ceiling)", classically_by="route depends on measured structure (reported below)", kind="hard-labeled-benchmark"),
    "knn_n31": dict(source="QASMBench (Li et al. 2023); quantum kNN, 31q",
        field_claim="QML benchmark", classically_by="statevector at n=31 (~32 GB) feasible; route reported below", kind="hard-labeled-benchmark"),
    "dnn_n33": dict(source="QASMBench (Li et al. 2023); quantum DNN, 33q",
        field_claim="QML benchmark", classically_by="statevector at n=33 (~128 GB, HPC) feasible; route reported below", kind="hard-labeled-benchmark"),
}

CLASSICAL_TIERS = {"CPU", "TENSOR", "HPC_FIRST"}


def stage_qasm():
    circuits = []
    circuits += gen_kicked_ising()
    for name, rel in QASMBENCH:
        src = os.path.join(QB, rel)
        if not os.path.exists(src):
            print(f"  MISSING in repo: {name} ({rel})", file=sys.stderr)
            continue
        dst = os.path.join(QASM_DIR, f"{name}.qasm")
        shutil.copyfile(src, dst)
        circuits.append((name, dst))
    return circuits


def run_one(name, path):
    try:
        p = subprocess.run([VENV_PY, os.path.join(HERE, "worker.py"), path],
                           capture_output=True, text=True, timeout=TIMEOUT_S)
        if p.returncode != 0:
            return {"name": name, "status": "ERROR", "error": (p.stderr.strip().splitlines() or ["?"])[-1][:300]}
        rec = json.loads(p.stdout.strip().splitlines()[-1])
        rec["name"] = name
        rec["status"] = "ok"
        return rec
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "TIMEOUT", "timeout_s": TIMEOUT_S}
    except Exception as e:
        return {"name": name, "status": "ERROR", "error": f"{type(e).__name__}: {e}"}


def main():
    circuits = stage_qasm()
    results = []
    for name, path in circuits:
        print(f"running {name} ...", flush=True)
        rec = run_one(name, path)
        m = META.get(name, {})
        rec.update({"source": m.get("source"), "field_claim": m.get("field_claim"),
                    "classically_simulated_by": m.get("classically_by"), "kind": m.get("kind")})
        if rec.get("status") == "ok":
            route = rec.get("route")
            rec["classical_tier"] = route in CLASSICAL_TIERS
            rec["consistent_with_classical_reachability"] = bool(route in CLASSICAL_TIERS)
        results.append(rec)
        st = rec.get("status")
        print(f"   -> {st} route={rec.get('route')} gov={rec.get('governing_estimator')} "
              f"tw=2^{rec.get('treewidth_log2')} mps=2^{rec.get('mps_bond_log2')} T={rec.get('t_count')} "
              f"({rec.get('elapsed_s')}s)", flush=True)

    ok = [r for r in results if r.get("status") == "ok"]
    classical = [r for r in ok if r.get("classical_tier")]
    escalate = [r for r in ok if r.get("route") == "ESCALATE"]
    field_qpu = [r for r in ok if r.get("kind") == "field-assumed-QPU"]
    field_qpu_classical = [r for r in field_qpu if r.get("classical_tier")]
    summary = {
        "total_circuits": len(results),
        "ran_ok": len(ok),
        "failed_or_timeout": len(results) - len(ok),
        "routed_classical_tier": len(classical),
        "routed_escalate": len(escalate),
        "field_assumed_qpu_circuits": len(field_qpu),
        "field_assumed_qpu_routed_classical": len(field_qpu_classical),
        "tier_breakdown": {t: sum(1 for r in ok if r.get("route") == t)
                           for t in ["CPU", "TENSOR", "HPC_FIRST", "ESCALATE"]},
    }
    payload = {"summary": summary, "results": results,
               "engine": "atlas-codex/HANDOFF_5ideas cost_atlas + route_adjudicator (REAL)",
               "note": "Offline research harness. Web n-cap bypassed (cost_atlas called directly); live cap untouched; nothing deployed."}
    out = os.path.join(HERE, "results.json")
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()

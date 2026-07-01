"""Phase 2: the genuine field-assumed-QPU circuits.

(1) Kim et al. kicked-Ising at the REAL hard regime (non-Clifford Rx angle).
    The phase-1 phi=pi/2 run was the exactly-SOLVABLE Clifford point (T=0) -- not
    the field-assumed-hard regime. Here theta_J=-pi/2 (Clifford ZZ, as in paper)
    and phi a NON-Clifford angle -> magic on every qubit, the actual hard case.
    Also emit the Clifford point, honestly labeled.
(2) Sycamore-scale RCS (Arute 2019 methodology via cirq), shallow + deep.
(3) Honest research probe: the TRUE MPS bond (uncapped beyond Atlas's default
    n>20 cap of 64) for the hard kicked-Ising, to test whether the circuit is
    genuinely low-entanglement (the basis of Tindall et al.'s TN reproduction)
    even though Atlas's DEFAULT config truncates at bond 64 and cannot certify it.

Merges into results.json (replacing the stale phi=pi/2 kicked entries).
"""
from __future__ import annotations
import os, sys, json, subprocess, math

HERE = os.path.dirname(os.path.abspath(__file__))
QASM_DIR = os.path.join(HERE, "qasm")
ENGINE = "HANDOFF_5ideas"
VENV_PY = ".atlas-venv/bin/python"
TIMEOUT_S = 900
sys.path.insert(0, HERE)
CLASSICAL_TIERS = {"CPU", "TENSOR", "HPC_FIRST"}

PHI_HARD = 0.9  # rad; non-multiple of pi/2 -> non-Clifford (representative of Kim et al. sweep interior)


def gen():
    from heavy_hex import kicked_ising_qasm
    from sycamore_rcs import rcs_qasm
    files = []

    f = os.path.join(QASM_DIR, "kicked_ising_127q_hard_5steps.qasm")
    open(f, "w").write(kicked_ising_qasm(n_steps=5, theta_J=-math.pi/2, phi=PHI_HARD))
    files.append(("kicked_ising_127q_hard_5steps", f))

    f = os.path.join(QASM_DIR, "kicked_ising_127q_clifford_point.qasm")
    open(f, "w").write(kicked_ising_qasm(n_steps=5, theta_J=-math.pi/2, phi=math.pi/2))
    files.append(("kicked_ising_127q_clifford_point", f))

    for d in (8, 20):
        f = os.path.join(QASM_DIR, f"sycamore_rcs_53q_depth{d}.qasm")
        open(f, "w").write(rcs_qasm(depth=d, seed=0))
        files.append((f"sycamore_rcs_53q_depth{d}", f))
    return files


META = {
    "kicked_ising_127q_hard_5steps": dict(
        source="Kim et al., Nature 618, 500 (2023) (127q Eagle kicked TFIM; non-Clifford Rx angle = genuine hard regime, theta_J=-pi/2, phi=0.9 rad)",
        field_claim="QPU 'utility'-beyond-brute-force-classical; THE flagship field-assumed-hard circuit",
        classically_by="Tindall, Fishman, Stoudenmire, Sels, PRX Quantum 5, 020332 (2024) via tensor networks; Begusic & Chan (2024); Liao et al.; Patra et al.",
        kind="field-assumed-QPU"),
    "kicked_ising_127q_clifford_point": dict(
        source="Kim et al., Nature 618, 500 (2023), evaluated at the exactly-SOLVABLE Clifford point (theta_J=-pi/2, phi=pi/2)",
        field_claim="control: the Clifford point is analytically/Stim-solvable, NOT the field's hard regime",
        classically_by="trivially: pure Clifford -> Stim poly-time (Aaronson-Gottesman 2004)",
        kind="control-clifford"),
    "sycamore_rcs_53q_depth8": dict(
        source="Sycamore-scale RCS (Arute et al., Nature 574, 505 (2019) methodology) via cirq supremacy generator; shallow depth 8",
        field_claim="random circuit sampling: the 2019 'quantum supremacy' family (genuinely high treewidth at depth)",
        classically_by="shallow RCS is TN-tractable; deep 53q RCS later classically spoofed by Pan & Zhang, PRL 129, 090502 (2022) and Gordon-Bell 2021 work",
        kind="field-assumed-QPU"),
    "sycamore_rcs_53q_depth20": dict(
        source="Sycamore-scale RCS (Arute et al. 2019 methodology) via cirq supremacy generator; supremacy-depth 20",
        field_claim="random circuit sampling at the 2019 supremacy depth (the original frontier claim)",
        classically_by="classically reproduced post-hoc by large tensor-network/HPC runs (Pan-Zhang PRL 2022; Liu et al. Gordon Bell 2021); genuinely high-treewidth",
        kind="field-assumed-QPU"),
}


def run_one(name, path):
    try:
        p = subprocess.run([VENV_PY, os.path.join(HERE, "worker.py"), path],
                           capture_output=True, text=True, timeout=TIMEOUT_S)
        if p.returncode != 0:
            return {"name": name, "status": "ERROR", "error": (p.stderr.strip().splitlines() or ["?"])[-1][:300]}
        rec = json.loads(p.stdout.strip().splitlines()[-1])
        rec["name"] = name; rec["status"] = "ok"
        return rec
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "TIMEOUT", "timeout_s": TIMEOUT_S}
    except Exception as e:
        return {"name": name, "status": "ERROR", "error": f"{type(e).__name__}: {e}"}


def mps_probe():
    """TRUE MPS bond for the hard kicked-Ising at increasing caps (uncapped beyond
    Atlas's default 64). If bond stays small, the circuit IS low-entanglement
    (Tindall TN-reachable) and Atlas's default cap is what blocks certification."""
    sys.path.insert(0, ENGINE)
    os.chdir(ENGINE)
    from atlas import safe_parse
    from ground_truth import mps_bond_log2
    from heavy_hex import kicked_ising_qasm
    n, circ, _ = safe_parse(kicked_ising_qasm(n_steps=5, theta_J=-math.pi/2, phi=PHI_HARD))
    out = []
    for cap in (64, 128, 256):
        try:
            b, trunc = mps_bond_log2(n, circ, max_bond=cap)
            out.append({"cap": cap, "bond_log2": round(b, 2), "bond": int(2**b), "truncated": bool(trunc)})
        except Exception as e:
            out.append({"cap": cap, "error": f"{type(e).__name__}: {e}"})
    return out


def main():
    files = gen()
    new = []
    for name, path in files:
        print(f"running {name} ...", flush=True)
        rec = run_one(name, path)
        m = META.get(name, {})
        rec.update({"source": m.get("source"), "field_claim": m.get("field_claim"),
                    "classically_simulated_by": m.get("classically_by"), "kind": m.get("kind")})
        if rec.get("status") == "ok":
            rec["classical_tier"] = rec.get("route") in CLASSICAL_TIERS
            rec["consistent_with_classical_reachability"] = bool(rec.get("route") in CLASSICAL_TIERS)
        new.append(rec)
        print(f"   -> {rec.get('status')} route={rec.get('route')} gov={rec.get('governing_estimator')} "
              f"tw=2^{rec.get('treewidth_log2')} mps=2^{rec.get('mps_bond_log2')}(trunc={rec.get('mps_truncated')}) "
              f"T={rec.get('t_count')} ({rec.get('elapsed_s')}s)", flush=True)

    print("MPS probe (true bond, kicked-Ising hard 5 steps) ...", flush=True)
    probe = mps_probe()
    print("   ", probe, flush=True)

    # merge into results.json: drop stale phi=pi/2 entries, add new
    rj = os.path.join(HERE, "results.json")
    payload = json.load(open(rj))
    drop = {"kicked_ising_127q_5steps", "kicked_ising_127q_20steps"}
    kept = [r for r in payload["results"] if r.get("name") not in drop]
    kept += new
    payload["results"] = kept
    payload["kicked_ising_hard_mps_probe"] = probe
    payload["kicked_ising_20steps_note"] = ("Trotter depth 20 at the Clifford point did not build the "
        "quimb tensor network on this machine (process killed / >900s) -> reported as not-run, not fabricated.")

    ok = [r for r in kept if r.get("status") == "ok"]
    classical = [r for r in ok if r.get("classical_tier")]
    escalate = [r for r in ok if r.get("route") == "ESCALATE"]
    fq = [r for r in ok if r.get("kind") == "field-assumed-QPU"]
    fqc = [r for r in fq if r.get("classical_tier")]
    payload["summary"] = {
        "total_circuits": len(kept), "ran_ok": len(ok), "failed_or_timeout": len(kept) - len(ok),
        "routed_classical_tier": len(classical), "routed_escalate": len(escalate),
        "field_assumed_qpu_circuits": len(fq), "field_assumed_qpu_routed_classical": len(fqc),
        "tier_breakdown": {t: sum(1 for r in ok if r.get("route") == t)
                           for t in ["CPU", "TENSOR", "HPC_FIRST", "ESCALATE"]},
    }
    json.dump(payload, open(rj, "w"), indent=2)
    print("\n=== MERGED SUMMARY ===")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()

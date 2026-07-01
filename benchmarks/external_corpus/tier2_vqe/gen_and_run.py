"""OFFLINE research harness (tier2_vqe): construct REPRESENTATIVE quantum-chemistry /
VQE circuits (hardware-efficient ansatz + UCCSD-style excitation circuits) and run
Atlas's REAL engine (safe_parse + cost_atlas + route_adjudicator) on each, recording
the actual route / treewidth / MPS bond / magic / governing estimator.

Honest framing: these are PARAMETRIC, representative of published VQE/chemistry
workloads (the circuits vendors demo for "quantum chemistry on a QC"); they are NOT
a specific paper's exact transpiled circuit. Random angles are fine for routing,
which depends on circuit STRUCTURE (entanglement / treewidth / T-magic), not the
specific parameter values.

Does NOT deploy. Bypasses the web n-cap by calling cost_atlas directly (research
only; live cap untouched). Writes ONLY under this tier2_vqe/ directory.
"""
from __future__ import annotations
import os, sys, json, time, math, random

HERE = os.path.dirname(os.path.abspath(__file__))
QASM_DIR = os.path.join(HERE, "qasm")
ENGINE = "HANDOFF_5ideas"
os.makedirs(QASM_DIR, exist_ok=True)

random.seed(1234)

from qiskit import QuantumCircuit  # noqa: E402
from qiskit import qasm2           # noqa: E402

CLASSICAL_TIERS = {"CPU", "TENSOR", "HPC_FIRST"}


# ---------------------------------------------------------------------------
# Circuit constructors (representative of published VQE / chemistry workloads)
# ---------------------------------------------------------------------------
def hea(n: int, reps: int, entanglement: str = "linear") -> QuantumCircuit:
    """Hardware-efficient ansatz: per layer = ry+rz on every qubit, then a CX
    entangling block. 'linear' = chain CX(i,i+1); 'full' = all-to-all CX (high
    entanglement). This is THE ansatz vendors demo for 'quantum chemistry on a QC'."""
    qc = QuantumCircuit(n)
    for _ in range(reps):
        for q in range(n):
            qc.ry(random.uniform(-math.pi, math.pi), q)
            qc.rz(random.uniform(-math.pi, math.pi), q)
        if entanglement == "linear":
            for q in range(n - 1):
                qc.cx(q, q + 1)
        elif entanglement == "full":
            for a in range(n):
                for b in range(a + 1, n):
                    qc.cx(a, b)
    # final rotation layer (standard in HEA)
    for q in range(n):
        qc.ry(random.uniform(-math.pi, math.pi), q)
        qc.rz(random.uniform(-math.pi, math.pi), q)
    return qc


def _single_excitation(qc: QuantumCircuit, p: int, q: int, theta: float):
    """Trotterized single-excitation exp(theta(a_p^ a_q - h.c.)) Jordan-Wigner
    pattern: CNOT ladder + rz core + uncompute (representative UCCSD structure)."""
    qc.cx(p, q)
    qc.rz(theta, q)
    qc.cx(p, q)


def _double_excitation(qc: QuantumCircuit, p: int, q: int, r: int, s: int, theta: float):
    """Trotterized double-excitation: 4-qubit CNOT staircase + rz core + uncompute.
    Captures the CX-ladder + rz structure of a UCCSD double term (representative)."""
    qc.cx(p, q)
    qc.cx(q, r)
    qc.cx(r, s)
    qc.rz(theta, s)
    qc.cx(r, s)
    qc.cx(q, r)
    qc.cx(p, q)


def uccsd_style(n: int, n_doubles: int, n_singles: int) -> QuantumCircuit:
    """UCCSD-style ansatz approximation for a small molecule mapped to n spin-orbitals.
    Hartree-Fock reference (X on occupied half) + a set of single and double
    excitation operators. Random orbital indices/angles; structure (CX ladders +
    rz) is what governs routing."""
    qc = QuantumCircuit(n)
    # Hartree-Fock reference: fill lower half of orbitals
    for q in range(n // 2):
        qc.x(q)
    occ = list(range(n // 2))
    virt = list(range(n // 2, n))
    for _ in range(n_doubles):
        if len(occ) >= 2 and len(virt) >= 2:
            p, q = random.sample(occ, 2)
            r, s = random.sample(virt, 2)
            _double_excitation(qc, p, q, r, s, random.uniform(-math.pi, math.pi))
    for _ in range(n_singles):
        p = random.choice(occ)
        r = random.choice(virt)
        _single_excitation(qc, p, r, random.uniform(-math.pi, math.pi))
    return qc


# ---------------------------------------------------------------------------
# Circuit catalog: ~12 across sizes / depths / entanglement
# ---------------------------------------------------------------------------
def build_catalog():
    cat = []  # (name, qc, meta)
    def M(circuit_type, scale, note):
        return dict(circuit_type=circuit_type, scale=scale, note=note)

    REP_NOTE = ("representative VQE/chemistry workload, commonly presented as a QC "
                "use-case; parametric (random angles), not a specific vendor's exact circuit")

    # Hardware-efficient ansatz, linear entanglement, across n and depth
    cat.append(("hea_linear_n8_d3",  hea(8, 3, "linear"),  M("HEA (ry/rz + linear CX)", "n=8, reps=3", REP_NOTE)))
    cat.append(("hea_linear_n12_d3", hea(12, 3, "linear"), M("HEA (ry/rz + linear CX)", "n=12, reps=3", REP_NOTE)))
    cat.append(("hea_linear_n16_d4", hea(16, 4, "linear"), M("HEA (ry/rz + linear CX)", "n=16, reps=4", REP_NOTE)))
    cat.append(("hea_linear_n20_d4", hea(20, 4, "linear"), M("HEA (ry/rz + linear CX)", "n=20, reps=4", REP_NOTE)))
    # Deep linear (more layers -> more T-magic from rz, deeper structure)
    cat.append(("hea_linear_n12_d8", hea(12, 8, "linear"), M("HEA (ry/rz + linear CX), deep", "n=12, reps=8", REP_NOTE)))

    # Hardware-efficient ansatz, FULL (all-to-all) entanglement -> high entanglement spread
    cat.append(("hea_full_n8_d3",  hea(8, 3, "full"),  M("HEA (ry/rz + all-to-all CX), high-entanglement", "n=8, reps=3", REP_NOTE)))
    cat.append(("hea_full_n12_d3", hea(12, 3, "full"), M("HEA (ry/rz + all-to-all CX), high-entanglement", "n=12, reps=3", REP_NOTE)))
    cat.append(("hea_full_n16_d3", hea(16, 3, "full"), M("HEA (ry/rz + all-to-all CX), high-entanglement", "n=16, reps=3", REP_NOTE)))
    cat.append(("hea_full_n20_d2", hea(20, 2, "full"), M("HEA (ry/rz + all-to-all CX), high-entanglement", "n=20, reps=2", REP_NOTE)))

    # UCCSD-style chemistry ansaetze at molecule-representative scales
    cat.append(("uccsd_h2_n4",    uccsd_style(4, n_doubles=1, n_singles=2),    M("UCCSD-style (CX ladders + rz)", "H2 ~ 4 spin-orbitals", REP_NOTE)))
    cat.append(("uccsd_lih_n12",  uccsd_style(12, n_doubles=6, n_singles=6),   M("UCCSD-style (CX ladders + rz)", "LiH ~ 12 spin-orbitals", REP_NOTE)))
    cat.append(("uccsd_beh2_n14", uccsd_style(14, n_doubles=10, n_singles=8),  M("UCCSD-style (CX ladders + rz)", "BeH2 ~ 14 spin-orbitals", REP_NOTE)))

    return cat


def run():
    sys.path.insert(0, ENGINE)
    os.chdir(ENGINE)  # atlas/ground_truth use relative 'src' path
    from atlas import safe_parse, cost_atlas  # noqa: E402

    catalog = build_catalog()
    results = []
    for name, qc, meta in catalog:
        qasm_text = qasm2.dumps(qc)
        qpath = os.path.join(QASM_DIR, f"{name}.qasm")
        with open(qpath, "w") as f:
            f.write(qasm_text)
        t0 = time.time()
        try:
            n, circ, warns = safe_parse(qasm_text)
            r = cost_atlas(n, circ)
            dt = round(time.time() - t0, 2)
            ra = r.get("route_adjudication") or {}
            costs = r.get("costs_log2") or {}
            route = ra.get("route")
            rec = {
                "name": name,
                "status": "ok",
                "circuit_type": meta["circuit_type"],
                "scale": meta["scale"],
                "n": n,
                "n_2q_gates": sum(1 for g in circ if g[0] in ("cx", "cz", "swap", "iswap", "cy", "ch", "crz", "cp", "rzz", "rxx", "ryy")),
                "n_gates": len(circ),
                "t_count": r.get("t_count"),
                "magic_log2": costs.get("fold(magic)"),
                "mps_bond_log2": costs.get("MPS(entangle)"),
                "mps_truncated": r.get("mps_truncated"),
                "treewidth_log2": costs.get("contraction(treewidth)"),
                "treewidth_exact": r.get("treewidth_exact"),
                "stim_clifford": r.get("stim_clifford"),
                "best_method": r.get("best_method"),
                "union_cost_log2": r.get("union_cost_log2"),
                "verdict": r.get("verdict"),
                "route": route,
                "governing_estimator": ra.get("governing_estimator"),
                "governing_cost_log2": ra.get("governing_cost_log2"),
                "confidence": (ra.get("confidence") or {}).get("label"),
                "single_estimator_baselines": ra.get("single_estimator_baselines"),
                "classical_tier": route in CLASSICAL_TIERS,
                "n_parse_warnings": len(warns),
                "elapsed_s": dt,
                "note": meta["note"],
            }
        except Exception as e:
            rec = {"name": name, "status": "ERROR", "error": f"{type(e).__name__}: {e}",
                   "circuit_type": meta["circuit_type"], "scale": meta["scale"], "note": meta["note"]}
        results.append(rec)
        print(f"{name:20s} -> {rec.get('status')} route={rec.get('route')} "
              f"gov={rec.get('governing_estimator')} tw=2^{rec.get('treewidth_log2')} "
              f"mps=2^{rec.get('mps_bond_log2')} T={rec.get('t_count')} ({rec.get('elapsed_s')}s)", flush=True)

    ok = [r for r in results if r.get("status") == "ok"]
    classical = [r for r in ok if r.get("classical_tier")]
    escalate = [r for r in ok if r.get("route") == "ESCALATE"]
    summary = {
        "total_circuits": len(results),
        "ran_ok": len(ok),
        "failed_or_error": len(results) - len(ok),
        "routed_classical_tier": len(classical),
        "routed_escalate": len(escalate),
        "tier_breakdown": {t: sum(1 for r in ok if r.get("route") == t)
                           for t in ["CPU", "TENSOR", "HPC_FIRST", "ESCALATE"]},
        "by_type": {},
    }
    for r in ok:
        ct = r["circuit_type"].split(" (")[0]
        d = summary["by_type"].setdefault(ct, {"n": 0, "classical": 0, "escalate": 0})
        d["n"] += 1
        d["classical"] += int(bool(r.get("classical_tier")))
        d["escalate"] += int(r.get("route") == "ESCALATE")

    payload = {
        "summary": summary,
        "results": results,
        "engine": "atlas-codex/HANDOFF_5ideas safe_parse + cost_atlas + route_adjudicator (REAL)",
        "circuit_provenance": ("All circuits are PARAMETRIC and constructed to be representative of "
                               "published VQE / quantum-chemistry workloads (hardware-efficient ansaetze "
                               "and UCCSD-style excitation circuits). They are NOT a specific paper's exact "
                               "transpiled circuit. Routing depends on circuit STRUCTURE (entanglement / "
                               "treewidth / T-magic), which is preserved regardless of the random angles used."),
        "note": ("Offline research harness. Web n-cap bypassed (cost_atlas called directly); live cap "
                 "untouched; nothing deployed. Outputs only under benchmarks/external_corpus/tier2_vqe/."),
    }
    out = os.path.join(HERE, "results.json")
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {out}")
    return payload


if __name__ == "__main__":
    run()

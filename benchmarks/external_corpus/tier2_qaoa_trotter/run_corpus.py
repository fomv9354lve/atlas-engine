"""OFFLINE research harness (tier2): run Atlas's REAL engine (cost_atlas +
route_adjudicator) on CONSTRUCTED circuits that are representative of published
QAOA / optimization and Trotterized Hamiltonian-simulation workloads -- two of
the most-cited near-term "quantum advantage" use-cases.

Honest thesis test: does CIRCUIT STRUCTURE (1D/area-law vs dense-2D/high-p), not
the headline "QAOA" or "Hamiltonian simulation" label, drive the classical
route Atlas chooses? Circuits are constructed-representative (parametric, random
angles), NOT lifted from a specific paper's exact instance -- labelled as such.

Does NOT deploy anything and adds no claim to the live site. Outputs are written
only under this directory.
"""
from __future__ import annotations
import os, sys, json, math, random, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
QASM_DIR = os.path.join(HERE, "qasm")
VENV_PY = ".atlas-venv/bin/python"
TIMEOUT_S = 600
CLASSICAL_TIERS = {"CPU", "TENSOR", "HPC_FIRST"}

os.makedirs(QASM_DIR, exist_ok=True)
random.seed(20260630)

HEADER = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[{n}];\n'


# ---------------------------------------------------------------- graph builders
def line_edges(n):
    """1D open chain (path). Treewidth 1 graph; low contraction width."""
    return [(i, i + 1) for i in range(n - 1)]


def grid_edges(rows, cols):
    """2D rectangular grid. Treewidth ~ min(rows, cols); higher contraction."""
    def idx(r, c):
        return r * cols + c
    e = []
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                e.append((idx(r, c), idx(r, c + 1)))
            if r + 1 < rows:
                e.append((idx(r, c), idx(r + 1, c)))
    return e


def dense_random_edges(n, p_edge):
    """Erdos-Renyi random graph (dense). High treewidth by construction."""
    e = []
    for i in range(n):
        for j in range(i + 1, n):
            if random.random() < p_edge:
                e.append((i, j))
    return e


# ----------------------------------------------------------- circuit generators
def qaoa_qasm(n, edges, p):
    """Standard QAOA MaxCut: per layer, Rzz(2*gamma) on each edge then Rx(2*beta)
    on every qubit; repeated p times. Start in |+>^n via H on all qubits."""
    s = [HEADER.format(n=n)]
    for q in range(n):
        s.append(f"h q[{q}];")
    for _ in range(p):
        gamma = random.uniform(0.1, 0.9)
        beta = random.uniform(0.1, 0.9)
        for (a, b) in edges:
            s.append(f"rzz({2*gamma}) q[{a}],q[{b}];")
        for q in range(n):
            s.append(f"rx({2*beta}) q[{q}];")
    return "\n".join(s) + "\n"


def trotter_tfim_qasm(n, edges, steps, dt=0.3):
    """Trotterized TFIM: each step = Rzz(2*J*dt) on every bond, then Rx(2*h*dt)
    on every site. ZZ coupling + transverse field."""
    s = [HEADER.format(n=n)]
    J, h = 1.0, 0.8
    for _ in range(steps):
        for (a, b) in edges:
            s.append(f"rzz({2*J*dt}) q[{a}],q[{b}];")
        for q in range(n):
            s.append(f"rx({2*h*dt}) q[{q}];")
    return "\n".join(s) + "\n"


def trotter_heisenberg_qasm(n, edges, steps, dt=0.3):
    """Trotterized Heisenberg XXZ: each step = Rxx+Ryy+Rzz on every bond, plus a
    small Rz field on every site."""
    s = [HEADER.format(n=n)]
    Jx, Jy, Jz, hz = 1.0, 1.0, 0.9, 0.2
    for _ in range(steps):
        for (a, b) in edges:
            s.append(f"rxx({2*Jx*dt}) q[{a}],q[{b}];")
            s.append(f"ryy({2*Jy*dt}) q[{a}],q[{b}];")
            s.append(f"rzz({2*Jz*dt}) q[{a}],q[{b}];")
        for q in range(n):
            s.append(f"rz({2*hz*dt}) q[{q}];")
    return "\n".join(s) + "\n"


# --------------------------------------------------------------- circuit specs
# (name, builder -> qasm text, structure label, metadata dict)
def build_specs():
    specs = []

    def add(name, text, meta):
        specs.append((name, text, meta))

    # ---- QAOA MaxCut: 1D / sparse line graphs (low treewidth) ----
    for n, p in [(16, 1), (20, 3), (24, 2)]:
        add(f"qaoa_line_n{n}_p{p}", qaoa_qasm(n, line_edges(n), p),
            dict(type="QAOA-MaxCut", structure="1D line graph (sparse, low treewidth)",
                 n=n, p=p, edges="path", note="QAOA on a 1D/sparse MaxCut instance"))

    # ---- QAOA MaxCut: dense / random graphs (higher treewidth) ----
    for n, p, pe in [(10, 1, 0.6), (16, 1, 0.6), (16, 3, 0.6), (20, 2, 0.55), (24, 2, 0.5)]:
        E = dense_random_edges(n, pe)
        add(f"qaoa_dense_n{n}_p{p}", qaoa_qasm(n, E, p),
            dict(type="QAOA-MaxCut", structure=f"dense Erdos-Renyi graph (high treewidth), |E|={len(E)}",
                 n=n, p=p, edges="dense-random", note="QAOA on a dense/random MaxCut instance"))

    # ---- Trotter: TFIM / Heisenberg on a 1D line (area-law -> MPS-friendly) ----
    add("trotter_tfim_line_n16_s4", trotter_tfim_qasm(16, line_edges(16), 4),
        dict(type="Trotter-TFIM", structure="1D line (area-law)", n=16, steps=4, edges="line"))
    add("trotter_tfim_line_n30_s5", trotter_tfim_qasm(30, line_edges(30), 5),
        dict(type="Trotter-TFIM", structure="1D line (area-law)", n=30, steps=5, edges="line"))
    add("trotter_heis_line_n20_s4", trotter_heisenberg_qasm(20, line_edges(20), 4),
        dict(type="Trotter-Heisenberg", structure="1D line (area-law)", n=20, steps=4, edges="line"))
    add("trotter_heis_line_n28_s5", trotter_heisenberg_qasm(28, line_edges(28), 5),
        dict(type="Trotter-Heisenberg", structure="1D line (area-law)", n=28, steps=5, edges="line"))

    # ---- Trotter: TFIM / Heisenberg on a 2D grid (higher treewidth) ----
    add("trotter_tfim_grid3x4_n12_s4", trotter_tfim_qasm(12, grid_edges(3, 4), 4),
        dict(type="Trotter-TFIM", structure="2D grid 3x4 (higher treewidth)", n=12, steps=4, edges="grid"))
    add("trotter_tfim_grid4x5_n20_s4", trotter_tfim_qasm(20, grid_edges(4, 5), 4),
        dict(type="Trotter-TFIM", structure="2D grid 4x5 (higher treewidth)", n=20, steps=4, edges="grid"))
    add("trotter_heis_grid4x4_n16_s4", trotter_heisenberg_qasm(16, grid_edges(4, 4), 4),
        dict(type="Trotter-Heisenberg", structure="2D grid 4x4 (higher treewidth)", n=16, steps=4, edges="grid"))
    add("trotter_heis_grid4x6_n24_s4", trotter_heisenberg_qasm(24, grid_edges(4, 6), 4),
        dict(type="Trotter-Heisenberg", structure="2D grid 4x6 (higher treewidth)", n=24, steps=4, edges="grid"))

    return specs


def stage_qasm(specs):
    staged = []
    for name, text, meta in specs:
        fn = os.path.join(QASM_DIR, f"{name}.qasm")
        with open(fn, "w") as f:
            f.write(text)
        staged.append((name, fn, meta))
    return staged


def run_one(name, path):
    try:
        p = subprocess.run([VENV_PY, os.path.join(HERE, "worker.py"), path],
                           capture_output=True, text=True, timeout=TIMEOUT_S)
        if p.returncode != 0:
            return {"name": name, "status": "ERROR",
                    "error": (p.stderr.strip().splitlines() or ["?"])[-1][:300]}
        rec = json.loads(p.stdout.strip().splitlines()[-1])
        rec["name"] = name
        rec["status"] = "ok"
        return rec
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "TIMEOUT", "timeout_s": TIMEOUT_S}
    except Exception as e:
        return {"name": name, "status": "ERROR", "error": f"{type(e).__name__}: {e}"}


def main():
    specs = build_specs()
    staged = stage_qasm(specs)
    results = []
    for name, path, meta in staged:
        print(f"running {name} ...", flush=True)
        rec = run_one(name, path)
        rec.update({
            "type": meta.get("type"),
            "structure": meta.get("structure"),
            "p_or_steps": meta.get("p", meta.get("steps")),
            "circuit_meta": meta,
            "label": "constructed-representative of published QAOA/Hamiltonian-simulation workloads",
        })
        if rec.get("status") == "ok":
            rec["classical_tier"] = rec.get("route") in CLASSICAL_TIERS
        results.append(rec)
        print(f"   -> {rec.get('status')} route={rec.get('route')} "
              f"gov={rec.get('governing_estimator')} tw=2^{rec.get('treewidth_log2')} "
              f"mps=2^{rec.get('mps_bond_log2')} T={rec.get('t_count')} "
              f"({rec.get('elapsed_s')}s)", flush=True)

    ok = [r for r in results if r.get("status") == "ok"]
    by_route = {t: sum(1 for r in ok if r.get("route") == t)
                for t in ["CPU", "TENSOR", "HPC_FIRST", "ESCALATE"]}
    by_struct = {}
    for r in ok:
        key = (r.get("type"), "1D/line" if "1D" in (r.get("structure") or "") else
               "grid" if "grid" in (r.get("structure") or "") else
               "dense" if "dense" in (r.get("structure") or "") else "other")
        by_struct.setdefault(f"{key[0]} | {key[1]}", {}).setdefault(r.get("route"), 0)
        by_struct[f"{key[0]} | {key[1]}"][r.get("route")] += 1

    summary = {
        "total_circuits": len(results),
        "ran_ok": len(ok),
        "failed_or_timeout": len(results) - len(ok),
        "route_distribution": by_route,
        "routed_classical_tier": sum(1 for r in ok if r.get("classical_tier")),
        "routed_escalate": by_route["ESCALATE"],
        "route_by_type_and_structure": by_struct,
    }
    payload = {
        "summary": summary,
        "results": results,
        "engine": "atlas-codex/HANDOFF_5ideas cost_atlas + route_adjudicator (REAL)",
        "note": ("Offline research harness. Circuits are constructed-representative of published "
                 "QAOA/Hamiltonian-simulation workloads (parametric, random angles), not lifted "
                 "from a specific paper instance. Web n-cap bypassed by calling cost_atlas directly; "
                 "live cap untouched; nothing deployed."),
    }
    out = os.path.join(HERE, "results.json")
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()

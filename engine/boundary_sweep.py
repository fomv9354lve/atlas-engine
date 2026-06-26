#!/usr/bin/env python3
"""boundary_sweep — explore the complexity space around a circuit and find where the
classical-simulation verdict crosses CPU -> TENSOR -> HPC_FIRST -> ESCALATE.

This is the honest, measured version of "generate a higher-complexity variant":
seeded by an input circuit's size (n, T-count), it sweeps an expander family upward
(long-range CX = non-local entanglement + cross-distributed T = magic) and reports,
via the real engine, the FIRST n at which each route class appears, plus the QASM of
the first genuinely-hard variant. No claim of classical impossibility — just where
the measured cost crosses each budget.

Used by webui /api/harden. CLI: python3 boundary_sweep.py [n0] [t0]
"""
from __future__ import annotations

import hashlib
import random
import re

from atlas import cost_atlas, safe_parse, to_qasm
try:
    from atlas_certificate import certificate as _cert
except Exception:
    _cert = None


def _seed(*p):
    return int.from_bytes(hashlib.md5("-".join(map(str, p)).encode()).digest()[:4], "big")


def build_expander(n, layers, t_total, seed=1):
    """H layers + random long-range CX (non-local entanglement) + distributed T."""
    rng = random.Random(_seed(n, layers, t_total, seed))
    ops = ["OPENQASM 2.0;", 'include "qelib1.inc";', f"qreg q[{n}];"]
    placed = 0
    for _ in range(layers):
        for q in range(n):
            ops.append(f"h q[{q}];")
        cand = []
        while len(cand) < n * 2:
            a, b = rng.randrange(n), rng.randrange(n)
            if a != b:
                cand.append((min(a, b), max(a, b)))
        rng.shuffle(cand)
        for a, b in cand[:n]:
            ops.append(f"cx q[{a}],q[{b}];")
        for q in range(n):
            if placed < t_total and rng.random() < 0.3:
                ops.append(f"t q[{q}];"); placed += 1
    while placed < t_total:
        ops.append(f"t q[{rng.randrange(n)}];"); placed += 1
    return "\n".join(ops) + "\n"


try:
    from atlas_timeout import cost_atlas_guarded as _cost   # fork+kill: el sweep no cuelga
except Exception:
    _cost = cost_atlas


def _route(qasm):
    n, circ, _ = safe_parse(qasm)
    r = _cost(n, circ, timeout_s=5) if _cost is not cost_atlas else cost_atlas(n, circ)
    ra = r.get("route_adjudication") or {}
    c = r.get("costs_log2") or {}
    return {"n": n, "route": ra.get("route"),
            "magic_log2": c.get("fold(magic)"), "mps_log2": c.get("MPS(entangle)"),
            "treewidth_log2": c.get("contraction(treewidth)")}


def parse_nt(qasm):
    m = re.search(r"qreg\s+\w+\[(\d+)\]", qasm or "")
    n = int(m.group(1)) if m else 10
    t = len(re.findall(r"(?m)^\s*t\s+q", qasm or "")) or max(8, n)
    return n, t


def sweep(n0=10, t0=16, n_max=44, step=4, layers=3, seed=1):
    """Sweep n upward; return the trajectory and the first variant per route class."""
    ORDER = ["CPU", "TENSOR", "HPC_FIRST", "ESCALATE"]
    traj, first = [], {}
    t = max(t0, 16)
    for n in range(max(6, n0), n_max + 1, step):
        q = build_expander(n, layers, t, seed)
        row = _route(q)
        traj.append(row)
        rt = (row["route"] or "").upper()
        if rt in ORDER and rt not in first:
            first[rt] = {"n": n, "qasm": q, **({"certificate": _cert(q)} if _cert else {})}
    # first genuinely-hard variant (first non-CPU)
    hard = next((first[r] for r in ("TENSOR", "HPC_FIRST", "ESCALATE") if r in first), None)
    # ruta del primer-duro: tomarla de la trayectoria ya computada (no re-correr cost_atlas)
    hard_route = next((row["route"] for row in traj if hard and row["n"] == hard["n"]), None)
    return {"seed_n": n0, "seed_t": t0, "trajectory": traj,
            "first_by_route": {k: {"n": v["n"]} for k, v in first.items()},
            "first_hard": (None if hard is None else
                           {"n": hard["n"], "route": hard_route, "qasm": hard["qasm"],
                            "certificate": hard.get("certificate")})}


def harden(qasm, **kw):
    """Seeded by the input circuit size, explore upward and return where it crosses."""
    n0, t0 = parse_nt(qasm)
    return sweep(n0=n0, t0=t0, **kw)


if __name__ == "__main__":
    import json
    import sys
    n0 = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    t0 = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    out = sweep(n0=n0, t0=t0)
    print(f"seed n={n0} t={t0} | expander family, sweep n -> route crossings\n")
    print(f"{'n':>4}{'route':<11}{'magic2^':>8}{'mps2^':>7}{'tw2^':>6}")
    for r in out["trajectory"]:
        print(f"{r['n']:>4}{str(r['route']):<11}{str(r['magic_log2']):>8}"
              f"{str(r['mps_log2']):>7}{str(r['treewidth_log2']):>6}")
    fh = out["first_hard"]
    print(f"\nfirst genuinely-hard variant: "
          + (f"n={fh['n']} route={fh['route']}" if fh else "none in range"))

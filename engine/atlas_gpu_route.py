"""atlas_gpu_route.py -- ADVISORY overlay: the GPU full-statevector classical route.

WHY THIS EXISTS (Part-3 gap addressed)
--------------------------------------
Atlas' route adjudicator (route_adjudicator.py) already prices a full statevector
on CPU/TENSOR/HPC nodes (SV_CPU_MAX_N=21, SV_TENSOR_MAX_N=27, HPC n<=~33). What it
does NOT surface as a first-class, named option is the *GPU* statevector route:
cuStateVec / cuQuantum / Qiskit-Aer-GPU push exact statevector simulation up to the
qubit count where 2^n complex amplitudes fit in GPU memory. This module is a thin,
ADVISORY overlay that, given a cost_atlas() result, asks one honest question:

    "Before you pay for a QPU at this n, would a single (or small multi-) GPU
     statevector simulator do the job classically for less money?"

It NEVER changes Atlas' verdict and it NEVER claims quantum advantage or classical
impossibility. It only adds a cheaper *classical* candidate to consider, which can
only ever *strengthen* a "do NOT buy QPU" recommendation and can never manufacture
a "yes buy" one. The harder direction (proving a QPU is necessary) remains gated by
BQP != BPP and is out of scope here.

THE ARITHMETIC (verified; this is the load-bearing fact, not a heuristic)
-------------------------------------------------------------------------
A dense statevector of n qubits in complex128 (the precision Aer/cuStateVec use by
default for exactness) costs exactly:

    bytes = 2^n * 16            # 16 bytes = two float64 (real, imag)

    n=30 -> 17.18 GB     (fits a single 24-40 GB GPU)
    n=32 -> 68.72 GB     (fits a single 80 GB GPU, e.g. A100/H100 80GB)
    n=33 -> 137.4 GB     (needs >=2x 80 GB GPUs -- multi-GPU NVLink/NCCL)
    n=34 -> 274.9 GB     (>=4x 80 GB GPUs)
    n=36 -> 1.10 TB      (>=16x 80 GB GPUs -- a node/cluster, not "a GPU")
    n=40 -> 17.59 TB     (a sizeable cluster; usually cheaper to use a tensor network)

Working-memory reality check (HONEST CAVEAT): a real simulator needs more than one
copy of the state. Gate application, measurement/sampling buffers, and (for some
backends) a scratch copy mean the *effective* ceiling is typically ~0.5x the naive
"fits exactly" bound. We expose a configurable WORKING_SET_OVERHEAD for this so the
advice does not over-promise the top of the band.

DYNAMIC FRONTIER (this is the dynamic-frontier knob)
----------------------------------------------------
GPU_MEM_BYTES_PER_DEVICE, MAX_GPUS_SINGLE_NODE, and WORKING_SET_OVERHEAD below are
CONSTANTS that MUST be updated as hardware/algorithms move. As of 2026-06 an 80 GB
device is the common large datacenter GPU; 141 GB (H200) and 192 GB (B200/MI300X)
exist and would raise the single-GPU ceiling -- bump GPU_MEM_BYTES_PER_DEVICE then.
Likewise, algorithmic progress (slicing, gate fusion, paged statevector to host RAM)
can extend the reach beyond raw device memory; treat every number here as a snapshot,
not a law. The frontier is data, not physics.
"""
from __future__ import annotations
import math

# ----------------------------------------------------------------------------- #
# DYNAMIC FRONTIER CONSTANTS -- UPDATE AS HARDWARE/ALGORITHMS IMPROVE.
# These are engineering parameters, NOT measured physical limits. Snapshot: 2026-06.
# ----------------------------------------------------------------------------- #
GPU_MEM_BYTES_PER_DEVICE = 80 * (1000 ** 3)   # 80 GB datacenter GPU (A100/H100 80GB).
                                              # Bump to 141e9 (H200) / 192e9 (B200) as they
                                              # become the assumed baseline.
MAX_GPUS_SINGLE_NODE = 8                       # typical dense GPU node (8x SXM via NVLink).
                                              # Beyond this you are in cluster/HPC territory
                                              # where a tensor-network route usually wins.
WORKING_SET_OVERHEAD = 2.0                     # >=1.0: how many state-sized buffers a real
                                              # simulator needs in practice (state + scratch
                                              # /sampling). 2.0 is conservative; lower it only
                                              # with backend-specific evidence.
BYTES_PER_AMPLITUDE = 16                        # complex128 = 2 x float64. Exact, not a knob.

# The QPU frontier Atlas uses elsewhere is self-defined (n>=33); GPU statevector
# overlaps and competes with QPU exactly in the n in [~28, ~36] band -- the same band
# where "should I buy a QPU?" actually gets asked. Below ~28 even a CPU/TENSOR node
# wins (see route_adjudicator SV_*_MAX_N); above the multi-GPU ceiling, statevector
# stops being the cheap classical route and tensor-network / declared-OOD takes over.
GPU_ADVICE_MIN_N = 22   # below this, CPU/TENSOR statevector already dominates; GPU is overkill.


def statevector_bytes(n: int) -> int:
    """Exact dense statevector size in bytes for n qubits in complex128. 2^n * 16."""
    return (1 << n) * BYTES_PER_AMPLITUDE


def _human_bytes(b: float) -> str:
    for unit, scale in (("TB", 1000.0 ** 4), ("GB", 1000.0 ** 3), ("MB", 1000.0 ** 2)):
        if b >= scale:
            return f"{b / scale:.2f} {unit}"
    return f"{b:.0f} B"


def gpus_required(n: int, working_set_overhead: float = WORKING_SET_OVERHEAD,
                  gpu_mem_bytes: int = GPU_MEM_BYTES_PER_DEVICE) -> int:
    """Honest count of GPU devices needed to hold the (working-set-inflated) statevector.

    Returns ceil(state_bytes * overhead / mem_per_device). Independent of any QPU claim.
    """
    need = statevector_bytes(n) * working_set_overhead
    return max(1, math.ceil(need / gpu_mem_bytes))


def gpu_feasibility(n: int) -> dict:
    """Pure-arithmetic feasibility of the GPU statevector route at n qubits.

    Returns the band classification and the device count, with no reference to the
    Atlas verdict. This is the factual core; gpu_route_advice() wraps policy around it.
    """
    raw = statevector_bytes(n)
    effective = raw * WORKING_SET_OVERHEAD
    ndev = gpus_required(n)
    single_cap = GPU_MEM_BYTES_PER_DEVICE
    node_cap = GPU_MEM_BYTES_PER_DEVICE * MAX_GPUS_SINGLE_NODE

    if effective <= single_cap:
        band = "single_gpu"            # one device holds it (with working-set overhead).
    elif effective <= node_cap:
        band = "multi_gpu_node"        # fits one dense node (<= MAX_GPUS_SINGLE_NODE devices).
    else:
        band = "beyond_single_node"    # cluster-scale; statevector is no longer the cheap route.

    return {
        "n": n,
        "statevector_bytes": raw,
        "statevector_human": _human_bytes(raw),
        "working_set_overhead": WORKING_SET_OVERHEAD,
        "effective_bytes": int(effective),
        "effective_human": _human_bytes(effective),
        "gpus_required": ndev,
        "band": band,
        "gpu_mem_bytes_per_device": GPU_MEM_BYTES_PER_DEVICE,
        "max_gpus_single_node": MAX_GPUS_SINGLE_NODE,
        "frontier_note": "constants are a 2026-06 snapshot; update as hardware/algorithms improve",
    }


def _route_of(route):
    """Accept either a route string or a route_adjudication dict."""
    if isinstance(route, dict):
        return route.get("route")
    return route


def gpu_route_advice(n: int, route, costs: dict | None = None) -> dict:
    """ADVISORY: should a GPU statevector be considered as the classical route at n?

    Parameters
    ----------
    n     : qubit count.
    route : Atlas route string ('CPU'/'TENSOR'/'HPC_FIRST'/'ESCALATE') OR the full
            route_adjudication dict from cost_atlas().
    costs : the costs_log2 dict (keys 'fold(magic)', 'MPS(entangle)',
            'contraction(treewidth)', 'spread(local)'). Used only to detect the
            Clifford-trivial / already-cheap case so we don't recommend a GPU where a
            laptop (or Stim) already wins. Optional.

    Returns a dict with: feasible (bool), band, gpus_required, memory figures,
    'recommend_gpu_over_qpu' (bool), 'advice' (string), and 'caveats' (list).

    HONESTY: 'recommend_gpu_over_qpu' True means ONLY "here is an exact classical
    route cheaper than a QPU -- do not buy the QPU for this." It is NEVER a claim that
    a QPU is or isn't *needed* in general, and NEVER a quantum-advantage statement.
    """
    feas = gpu_feasibility(n)
    rt = _route_of(route)
    caveats: list[str] = []

    # Is the circuit already trivially classical (so GPU is the wrong tool)?
    clifford_trivial = False
    cheap_already = False
    if costs:
        magic = costs.get("fold(magic)")
        # Clifford => Stim simulates in poly time; a GPU statevector is wasted money.
        if magic is not None and magic <= 0.0:
            clifford_trivial = True
        # Already-cheap classical routes (CPU/TENSOR) make GPU statevector overkill.
        if rt in ("CPU", "TENSOR"):
            cheap_already = True
    elif rt in ("CPU", "TENSOR"):
        cheap_already = True

    in_n_band = n >= GPU_ADVICE_MIN_N
    fits = feas["band"] in ("single_gpu", "multi_gpu_node")

    recommend = bool(in_n_band and fits and not clifford_trivial and not cheap_already)

    # Build the advice string honestly per case.
    if clifford_trivial:
        advice = ("Circuit is Clifford-trivial (t_count/magic = 0): exact via Stim in "
                  "polynomial time on a CPU. A GPU statevector would be wasted spend; "
                  "definitely do NOT buy a QPU for this.")
    elif n < GPU_ADVICE_MIN_N:
        advice = (f"n={n} is below the GPU-relevant band (< {GPU_ADVICE_MIN_N}); a CPU/TENSOR "
                  "statevector already wins (see route_adjudicator SV thresholds). GPU not needed.")
    elif cheap_already:
        advice = (f"Atlas already routes this to {rt} (cheap classical). A GPU statevector is an "
                  "available exact fallback but is overkill here; no QPU purchase is warranted.")
    elif feas["band"] == "single_gpu":
        advice = (f"A SINGLE {_human_bytes(feas['gpu_mem_bytes_per_device'])} GPU statevector "
                  f"({feas['statevector_human']} state, ~{feas['effective_human']} with working set) "
                  f"is an exact classical route at n={n}. This is almost certainly cheaper than QPU "
                  "time/queue -- do NOT buy a QPU for this circuit.")
    elif feas["band"] == "multi_gpu_node":
        advice = (f"A MULTI-GPU statevector needs ~{feas['gpus_required']} x "
                  f"{_human_bytes(feas['gpu_mem_bytes_per_device'])} GPUs "
                  f"(state {feas['statevector_human']}, ~{feas['effective_human']} with working set) "
                  f"on a single node at n={n}. Likely still cheaper than QPU access; weigh the "
                  "rental cost of the GPU node vs. QPU shot/queue pricing before buying QPU.")
        caveats.append("Multi-GPU statevector cost is sensitive to GPU rental pricing and "
                       "interconnect (NVLink/NCCL) efficiency; the 'cheaper than QPU' claim is "
                       "a candidate, not a guarantee, in this band.")
    else:  # beyond_single_node
        advice = (f"At n={n} the statevector is {feas['statevector_human']} "
                  f"(~{feas['effective_human']} with working set), needing ~{feas['gpus_required']} GPUs "
                  "-- beyond a single dense node. GPU statevector is NO LONGER the cheap classical "
                  "route here; defer to the tensor-network / MPS estimate, and Atlas declines exact "
                  "classical ground truth (OOD).")
        caveats.append("Above the multi-GPU-node ceiling, a tensor-network contraction (treewidth) "
                       "or truncated MPS may be the only classical option, and treewidth here is a "
                       "GREEDY UPPER bound -- not a proof of tractability.")

    # Always-on honesty about what this overlay is and isn't.
    caveats.append("This is an exact CLASSICAL route only. It can strengthen a 'do NOT buy QPU' "
                   "verdict; it can NEVER establish that a QPU IS needed (that would require "
                   "BQP != BPP) and makes no quantum-advantage claim.")
    caveats.append("Statevector simulates the full state but is exponential in n; it bypasses the "
                   "magic/entanglement structure entirely. For shallow/low-entanglement circuits a "
                   "tensor-network route may be far cheaper than even a single GPU.")
    caveats.append("Memory bound is exact (2^n * 16 B); the GPU/node ceiling and working-set "
                   "overhead are a 2026-06 hardware snapshot and must be re-checked over time.")

    return {
        "route_considered": "GPU_STATEVECTOR",
        "n": n,
        "atlas_route": rt,
        "feasible_classical_gpu": fits,
        "band": feas["band"],
        "gpus_required": feas["gpus_required"],
        "statevector_bytes": feas["statevector_bytes"],
        "statevector_human": feas["statevector_human"],
        "effective_human": feas["effective_human"],
        "clifford_trivial": clifford_trivial,
        "recommend_gpu_over_qpu": recommend,
        "advice": advice,
        "caveats": caveats,
        "frontier_constants": {
            "GPU_MEM_BYTES_PER_DEVICE": GPU_MEM_BYTES_PER_DEVICE,
            "MAX_GPUS_SINGLE_NODE": MAX_GPUS_SINGLE_NODE,
            "WORKING_SET_OVERHEAD": WORKING_SET_OVERHEAD,
            "GPU_ADVICE_MIN_N": GPU_ADVICE_MIN_N,
            "note": "DYNAMIC FRONTIER -- update as hardware/algorithms improve.",
        },
    }


def _demo():
    print("=" * 78)
    print("atlas_gpu_route -- GPU statevector classical-route advisory (ADVISORY ONLY)")
    print(f"frontier: {_human_bytes(GPU_MEM_BYTES_PER_DEVICE)}/GPU, "
          f"<= {MAX_GPUS_SINGLE_NODE} GPUs/node, working-set x{WORKING_SET_OVERHEAD}")
    print("=" * 78)

    # Self-check the load-bearing arithmetic.
    checks = {30: 17.18e9, 32: 68.72e9, 33: 137.44e9, 36: 1.10e12}
    print("\n[arithmetic self-check: 2^n * 16 bytes]")
    for n, expect in checks.items():
        got = statevector_bytes(n)
        ok = abs(got - expect) / expect < 0.01
        print(f"  n={n:>2}: {_human_bytes(got):>10}  ({got} B)  {'OK' if ok else 'MISMATCH'}")

    # Representative scenarios spanning the bands.
    scenarios = [
        ("Clifford n=30 (Stim-trivial)", 30, "TENSOR", {"fold(magic)": 0.0, "MPS(entangle)": 4.0}),
        ("small n=18 magic circuit",     18, "CPU",    {"fold(magic)": 6.0}),
        ("n=30 magic, HPC-routed",       30, "HPC_FIRST", {"fold(magic)": 40.0}),
        ("n=32 magic, escalated",        32, "ESCALATE",  {"fold(magic)": 80.0}),
        ("n=33 magic, escalated",        33, "ESCALATE",  {"fold(magic)": 90.0}),
        ("n=36 magic, escalated",        36, "ESCALATE",  {"fold(magic)": 120.0}),
        ("n=40 magic, escalated",        40, "ESCALATE",  {"fold(magic)": 160.0}),
    ]
    for label, n, route, costs in scenarios:
        a = gpu_route_advice(n, route, costs)
        print(f"\n--- {label} ---")
        print(f"  band={a['band']}  gpus_required={a['gpus_required']}  "
              f"state={a['statevector_human']} (eff {a['effective_human']})")
        print(f"  recommend_gpu_over_qpu={a['recommend_gpu_over_qpu']}")
        print(f"  advice: {a['advice']}")


if __name__ == "__main__":
    _demo()

#!/usr/bin/env python3
"""atlas_timeout — per-circuit wall-clock guard for cost_atlas (P1).

A pathological circuit (dense, large n) can make quimb/cotengra build unbounded
tensors and HANG. The hang is in C code, so signal.SIGALRM cannot interrupt it —
the only robust kill is a separate process. This runs cost_atlas in a forked child
and, if it exceeds the budget, TERMINATES it and returns an HONEST degraded verdict
("compute-bound -> defer to HPC") instead of hanging the caller. The engine never
blocks; an over-budget circuit is reported as exactly that, not silently dropped.

cost_atlas_guarded(n, circ, timeout_s=20) -> the cost_atlas dict, or a degraded dict
with route_adjudication.route = HPC_FIRST and compute_bound = True.
"""
from __future__ import annotations

import multiprocessing as _mp

from atlas import cost_atlas


def _worker(n, circ, q):
    try:
        q.put(("ok", cost_atlas(n, circ)))
    except Exception as e:                       # estimator error -> report, do not hang
        q.put(("err", f"{type(e).__name__}: {str(e)[:200]}"))


def _degraded(n, reason):
    return {
        "compute_bound": True,
        "route_adjudication": {
            "route": "HPC_FIRST", "governing_estimator": "compute-bound",
            "governing_cost_log2": None,
            "governing_reason": reason,
            "confidence": {"label": "low", "score": 0}},
        "costs_log2": {}, "verdict": "COMPUTE-BOUND: " + reason,
        "n": n, "tractable": None,
        "note": "the classical estimators exceeded the wall-clock budget for this "
                "circuit; this is an operational deferral (defer to HPC / longer budget), "
                "NOT a hardness claim."}


def cost_atlas_guarded(n, circ, timeout_s: float = 20.0):
    """cost_atlas with a hard wall-clock cap. Degrades (never hangs) on timeout."""
    try:
        ctx = _mp.get_context("fork")           # fork: child inherits imports, no re-import cost
    except (ValueError, AttributeError):
        return cost_atlas(n, circ)              # no fork available -> run inline (best effort)
    q = ctx.Queue()
    p = ctx.Process(target=_worker, args=(n, circ, q), daemon=True)
    p.start()
    p.join(timeout_s)
    if p.is_alive():                            # over budget -> kill the stuck child
        p.terminate(); p.join(1.0)
        if p.is_alive():
            p.kill()
        return _degraded(n, f"estimators exceeded {timeout_s:.0f}s wall-clock budget")
    try:
        tag, payload = q.get_nowait()
    except Exception:
        return _degraded(n, "worker produced no result (crash/OOM)")
    return payload if tag == "ok" else _degraded(n, "estimator error: " + str(payload))


if __name__ == "__main__":
    import os, sys, time
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
    sys.path.insert(0, os.path.dirname(__file__))
    # Demo: supply a QASM string via stdin, or run atlas_run.py for the full CLI.
    print("atlas_timeout: cost_atlas_guarded wrapper loaded — import and call cost_atlas_guarded(n, circ).")

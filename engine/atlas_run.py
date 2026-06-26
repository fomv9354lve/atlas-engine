#!/usr/bin/env python3
"""atlas_run — CLI: QASM on stdin -> full analysis JSON on stdout.

Lets the web server DELEGATE large circuits (n>60) to a local subprocess instead of
rejecting them: subprocess is killable on timeout and thread-safe (unlike fork-from-
thread), so the threaded web server can offer deep local analysis without hanging.

Usage:  echo "<qasm>" | python3 atlas_run.py
Returns cost_atlas(...) merged with certificate(...). On parse/engine error, prints a
JSON error object (never hangs the caller — the caller wraps this in a wall-clock timeout).
"""
from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    qasm = sys.stdin.read()
    try:
        from atlas import cost_atlas, safe_parse
        n, circ, warns = safe_parse(qasm)
        r = cost_atlas(n, circ)
        r["n"] = n
        r["warnings"] = warns
        try:
            from atlas_certificate import certificate
            r["certificate"] = certificate(qasm)
        except Exception as e:
            r["certificate"] = None
            r["certificate_err"] = str(e)[:200]
        print(json.dumps(r))
    except Exception as e:
        print(json.dumps({"error": f"{type(e).__name__}: {str(e)[:300]}"}))


if __name__ == "__main__":
    main()

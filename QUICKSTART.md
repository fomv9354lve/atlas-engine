# Atlas — Quantum Compute Triage · Local Engine (Free · Full Power)

Run the full Atlas engine **on your own machine**. Your circuits never leave your network —
ideal for sensitive or air-gapped work. No account, no usage limits, no 30-second server cap.

© 2026 Fco. Osvaldo Morales Vilchis · **Apache 2.0** (see `LICENSE` / `NOTICE`).

---

## What you get

- The same triage engine that powers [atlas.krenniq.com](https://atlas.krenniq.com), but **full power**:
  - exact statevector up to n ≤ 22, scalable estimators (MPS bond via quimb, treewidth via
    cotengra, Clifford via Stim) at any n;
  - failure-mode-aware **route adjudication** (CPU / TENSOR / HPC / ESCALATE) with calibrated confidence;
  - the **local web UI** (visual builder, evidence ledger, hardware reachability) at `http://127.0.0.1`.
- **No server throttle.** Heavy circuits run to completion on *your* hardware (`ATLAS_TIMEOUT_S`,
  default 1 h) instead of degrading at 30 s like the public demo.

---

## Install & run (≈2 minutes)

Requires **Python 3.10+**.

```bash
# 1. dependencies (numpy, stim, quimb, cotengra, qiskit)
python3 -m pip install -r requirements.txt

# 2. launch — opens http://127.0.0.1:8791 in your browser
python3 atlas_local.py
```

That's it. Paste OpenQASM, or use the visual **Build** panel, and analyze.

### Command-line (no browser, scriptable)

```bash
echo 'OPENQASM 2.0; include "qelib1.inc"; qreg q[5]; h q[0]; cx q[0],q[1]; t q[2];' \
  | python3 engine/atlas_run.py
# -> JSON verdict on stdout (route, estimators, confidence)
```

---

## Notes

- **100% local.** `atlas_local.py` binds `127.0.0.1` only; nothing is sent to any server.
- **Full-power timeout.** Set `ATLAS_TIMEOUT_S` to change the per-circuit budget (seconds);
  the public demo uses 30, here it defaults to 3600.
- **Optional — Ask Chat (Claude).** Disabled by default; if you set `ANTHROPIC_API_KEY`, the in-app
  "Ask Chat" sends the *numeric outputs* (not your raw circuit) to Anthropic. Clearly indicated in the UI.
- **Scope.** Atlas is a compute-cost *triage* (decision-support diagnostic), **not** a proof of
  simulability or quantum advantage. Verdicts in the borderline calibration zone are flagged as such.

## Security & robustness

The classifier was audited adversarially (0 false-security verdicts across irrational rotations,
T-identity camouflage, maximal entanglement, mid-circuit measurements, permutation camouflage); a
permanent regression test (`benchmarks/adversarial_attack.py`) guards every change.

---

Questions / issues: open an issue at https://github.com/fomv9354lve/atlas-engine/issues · [krenniq.com](https://krenniq.com)

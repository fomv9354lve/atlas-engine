#!/usr/bin/env python3
"""atlas_benchmark_bundle — the auditable benchmark artifact (diligence ask).

A reviewer's repeated request: make "2517 certified · Atlas 0.996" reproducible from
the product. This computes, from the certified CSVs, a self-contained JSON bundle with
everything needed to audit the claim: corpus size + hash, the route confusion matrix,
the metric DEFINITION (0.996 = route-correctness 2506/2517, not 'accuracy on 1 error'),
the false-safety count with a Wilson 95% CI on the small hard subset, and the
single-estimator baselines that justify the multi-method value. No new measurement —
it reads the committed oracle-certified rows.

bundle() -> dict (JSON-serializable). Served at /api/benchmark.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = None
for _base in (ROOT, *ROOT.parents[:2]):
    if (_base / "benchmarks" / "results_scaled").is_dir():
        CSV_DIR = _base / "benchmarks" / "results_scaled"
        break
CSV_DIR = CSV_DIR or (ROOT / "benchmarks" / "results_scaled")

CHEAP = {"cpu", "tensor"}
HARD = {"hpc_first", "escalate"}


def _cls(x):
    return (x or "").strip().lower()


def _wilson(k, n, z=1.96):
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return [round(max(0.0, (c - m) / d), 4), round(min(1.0, (c + m) / d), 4)]


def bundle():
    rows, files, h = [], [], hashlib.sha256()
    for f in sorted(glob.glob(str(CSV_DIR / "scaled_results*.csv"))):
        data = Path(f).read_bytes()
        h.update(data)
        files.append({"file": Path(f).name, "sha256": hashlib.sha256(data).hexdigest()[:16]})
        rows += [r for r in csv.DictReader(Path(f).open(encoding="utf-8"))
                 if _cls(r.get("oracle_certified")) == "true"]
    n = len(rows)
    if n == 0:
        return {"error": "no certified rows under " + str(CSV_DIR)}

    classes = ["cpu", "tensor", "hpc_first", "escalate"]
    confusion = {a: {b: 0 for b in classes} for a in classes}
    for r in rows:
        o, a = _cls(r["oracle_route"]), _cls(r["atlas_route_class"])
        if o in confusion and a in confusion[o]:
            confusion[o][a] += 1
    correct = sum(_cls(r["atlas_route_class"]) == _cls(r["oracle_route"]) for r in rows)
    fs = [r for r in rows if _cls(r["atlas_route_class"]) in CHEAP and _cls(r["oracle_route"]) in HARD]
    fa = [r for r in rows if _cls(r["atlas_route_class"]) in HARD and _cls(r["oracle_route"]) in CHEAP]
    hard_cases = [r for r in rows if _cls(r["oracle_route"]) in HARD]

    # single-estimator baselines (only on the slice that has those columns)
    base = {}
    for col, name in [("treewidth_only_class", "treewidth_only"),
                      ("mps_only_class", "mps_only"), ("magic_only_class", "magic_only")]:
        slc = [r for r in rows if r.get(col)]
        if slc:
            base[name] = {
                "n": len(slc),
                "false_safety": sum(_cls(r[col]) in CHEAP and _cls(r["oracle_route"]) in HARD for r in slc),
                "false_alarm": sum(_cls(r[col]) in HARD and _cls(r["oracle_route"]) in CHEAP for r in slc)}

    return {
        "schema": "atlas_benchmark_bundle/v1",
        "corpus": {"certified_circuits": n, "files": files,
                   "combined_sha256": h.hexdigest()[:16],
                   "labels_source": "oracle de exactitud: Stim (Clifford) / MPS no-truncado / statevector — "
                                    "etiqueta de ruta por coste exacto medido, no humano",
                   "train_test_split": "el benchmark es EVALUACIÓN (no entrenamiento): Atlas no se ajusta al "
                                       "corpus; la garantía conformal usa split selección/validación (ver atlas_conformal)"},
        "definitions": {
            "false_safety": "atlas rutea BARATO (cpu/tensor) un circuito que el oracle certifica DURO "
                            "(hpc/escalate) — el error peligroso (decir 'fácil' a algo que no lo es)",
            "false_alarm": "atlas rutea DURO un circuito que el oracle certifica BARATO — error conservador (caro, no peligroso)",
            "route_correctness": "atlas_route_class == oracle_route_class sobre el corpus certificado",
            "CHEAP": ["cpu", "tensor"], "HARD": ["hpc_first", "escalate"]},
        "metric_definition": {
            "atlas_0996": "route-correctness = (atlas_route_class == oracle_route) / certified",
            "value": round(correct / n, 4), "correct": correct, "of": n,
            "note": "11 disagreements: 1 false-safety + 10 safe-direction (cpu<->tensor) under-routes; "
                    "this is accuracy over ALL certified, not '1 error'."},
        "confusion_matrix_oracle_rows_x_atlas_cols": confusion,
        "errors": {
            "false_safety": {"count": len(fs), "of_all": n,
                             "of_hard_verified": len(hard_cases),
                             "rate_hard_verified": round(len(fs) / max(1, len(hard_cases)), 4),
                             "wilson_ci95_hard_verified": _wilson(len(fs), len(hard_cases)),
                             "ci_warning": "small-n: the hard-verified subset is tiny; CI is wide",
                             "ids": [r["id"] for r in fs][:10]},
            "false_alarm": {"count": len(fa)}},
        "single_estimator_baselines": base,
        "multi_method_value": "Atlas (min over methods) vs each single estimator's failure mode; "
                              "the composition is what avoids both false-safety and false-alarm.",
        "scope": {"oracle_basis": "exact only (Stim Clifford / non-truncated MPS / statevector)",
                  "escalate_unmeasured": "the genuinely quantum-hard regime has NO classical "
                                         "ground truth (BQP!=BPP); false-safety there is unmeasurable",
                  "not_claimed": ["classical impossibility", "quantum advantage"]},
        "reproduce": "python3 engine/atlas_benchmark_bundle.py  +  "
                     "python3 engine/atlas_conformal.py (held-out conformal guarantee)"}


if __name__ == "__main__":
    import json
    print(json.dumps(bundle(), indent=1))

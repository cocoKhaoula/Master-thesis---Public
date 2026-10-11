"""CloudFormation drift detection baseline (Section 6.1).

Drift detection is triggered by the harness inside each window, while the fault is
active (data/baselines/cfn_drift/<window>.json). Here its result is converted into a
prediction: any drifted resource is a reported anomaly, and each property difference is
a root-cause candidate. Drift detection reports *that* the live state differs, not
whether the difference caused a symptom - silent drift is therefore a false positive.
"""
from __future__ import annotations

from typing import Any


def _resource_to_function(functions_cfg: dict) -> dict[str, tuple[str, str]]:
    m = {}
    for key, f in functions_cfg.items():
        m[f["logical_id"]] = (key, "CONFIG")
        m[f["role_logical_id"]] = (key, "IAM")
    return m


def predict(drift: dict[str, Any], functions_cfg: dict) -> dict[str, Any]:
    if "drifted_resources" not in drift:
        return {"anomaly": False, "function": None, "root_cause_layer": "NONE", "candidates": [],
                "detected_at": None, "error": drift.get("error")}
    resources = drift["drifted_resources"]
    if not resources:
        return {"anomaly": False, "function": None, "root_cause_layer": "NONE", "candidates": [],
                "detected_at": None}
    mapping = _resource_to_function(functions_cfg)
    candidates = []
    for r in resources:
        for d in r["differences"] or [{"path": "", "expected": None, "actual": None, "type": r["status"]}]:
            candidates.append(f"{r['logical_id']} {d['path']} {d['type']} expected={d['expected']} actual={d['actual']}")
    fn, layer = mapping.get(resources[0]["logical_id"], (None, "CONFIG"))
    return {"anomaly": True, "function": fn, "root_cause_layer": layer, "candidates": candidates[:3],
            "detected_at": drift["finished"]}

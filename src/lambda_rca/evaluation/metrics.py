"""Evaluation metrics (thesis Section 2.6, equations 2.1-2.6, and Appendix F).

All functions are pure and operate on lists of dictionaries so that they can be
unit-tested against the worked example of Table F.1 (tests/test_metrics.py).
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from ..labels import artifact_matches, normalise


def safe_div(a: float, b: float) -> float:
    return a / b if b else float("nan")


# ------------------------------------------------------------------ detection
def confusion(pairs: Iterable[tuple[dict, dict]]) -> dict[str, int]:
    """pairs of (label, prediction). Symptomatic windows are positive; normal and
    silent-drift windows are negative (Section 2.6)."""
    tp = fp = tn = fn = 0
    for label, pred in pairs:
        if label["symptomatic"]:
            tp += pred["anomaly"]
            fn += not pred["anomaly"]
        else:
            fp += pred["anomaly"]
            tn += not pred["anomaly"]
    return {"TP": tp, "FP": fp, "TN": tn, "FN": fn}


def detection_metrics(c: dict[str, int]) -> dict[str, float]:
    precision = safe_div(c["TP"], c["TP"] + c["FP"])          # (2.1)
    recall = safe_div(c["TP"], c["TP"] + c["FN"])             # (2.2)
    fpr = safe_div(c["FP"], c["FP"] + c["TN"])                # (2.3)
    f1 = safe_div(2 * precision * recall, precision + recall) if not math.isnan(precision + recall) else float("nan")
    return {"precision": precision, "recall": recall, "fpr": fpr, "f1": f1}


# ------------------------------------------------------------------ localisation
def function_matches(label: dict, answered: str | None, functions_cfg: dict) -> bool:
    """The agent sees physical function names (e.g. lambda-rca-bench-CrudApiFunction-Ab12);
    the label stores the short key (crud-api). Match on the key or the logical id."""
    if not answered or not label.get("function"):
        return False
    a = normalise(answered)
    f = functions_cfg.get(label["function"], {})
    return normalise(label["function"]) in a or bool(f.get("logical_id") and normalise(f["logical_id"]) in a)


def level1_correct(label: dict, pred: dict, functions_cfg: dict) -> bool:
    """Level 1: correct layer and function (Section 2.6)."""
    return (pred.get("root_cause_layer") in label["accepted_layers"]
            and function_matches(label, pred.get("function"), functions_cfg))


def level2_hit_at_k(label: dict, pred: dict, k: int, functions_cfg: dict) -> bool:
    """Level 2: the exact artifact is among the first k candidates (eq. 2.4). The
    function must also be correct, because e.g. OUTPUT_BUCKET exists in three functions."""
    if not function_matches(label, pred.get("function"), functions_cfg):
        return False
    return any(artifact_matches(c, label["artifact_match"]) for c in (pred.get("candidates") or [])[:k])


def localisation_metrics(pairs: list[tuple[dict, dict]], functions_cfg: dict) -> dict[str, float]:
    """Computed only on detected symptomatic incidents (N = TP)."""
    detected = [(l, p) for l, p in pairs if l["symptomatic"] and p["anomaly"]]
    n = len(detected)
    return {
        "n_detected": n,
        "level1": safe_div(sum(level1_correct(l, p, functions_cfg) for l, p in detected), n),
        "top1": safe_div(sum(level2_hit_at_k(l, p, 1, functions_cfg) for l, p in detected), n),
        "top3": safe_div(sum(level2_hit_at_k(l, p, 3, functions_cfg) for l, p in detected), n),
    }


# ------------------------------------------------------------------ cost and time
def cost_usd(input_tokens: int, output_tokens: int, pricing: dict[str, Any]) -> float:
    """(2.6): Cost(i) = T_in * p_in + T_out * p_out."""
    return (input_tokens * pricing["input_per_million"] + output_tokens * pricing["output_per_million"]) / 1e6


def ttd_minutes(start_iso: str, detected_iso: str | None) -> float:
    """(2.5): TTD = t(first correct detection) - t(injection)."""
    if not detected_iso:
        return float("nan")
    from ..io import parse_iso
    import pandas as pd
    s = parse_iso(start_iso)
    d = pd.Timestamp(detected_iso)
    d = d.tz_localize("UTC") if d.tzinfo is None else d.tz_convert("UTC")
    return (d.to_pydatetime() - s).total_seconds() / 60.0

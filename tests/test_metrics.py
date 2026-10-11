"""Reproduces the worked example of thesis Table F.1."""
import math

import pytest

from lambda_rca.evaluation.metrics import (confusion, cost_usd, detection_metrics, level1_correct,
                                           level2_hit_at_k, localisation_metrics, ttd_minutes)

FUNCS = {"crud-api": {"logical_id": "CrudApiFunction"}, "uploader": {"logical_id": "UploaderFunction"}}


def label(symptomatic=True):
    return {"symptomatic": symptomatic, "function": "crud-api", "accepted_layers": ["IAM"],
            "artifact_match": [["putitem"]], "fault_type": "F1"}


def answer(anomaly, cands=(), layer="IAM", fn="lambda-rca-bench-CrudApiFunction-AbC123"):
    return {"anomaly": anomaly, "root_cause_layer": layer, "function": fn, "candidates": list(cands)}


def table_f1_pairs():
    pairs = []
    # 54 detected symptomatic incidents: 30 ranked first, 12 more in top-3, 12 missed
    for _ in range(30):
        pairs.append((label(), answer(True, ["dynamodb:PutItem missing", "x", "y"])))
    for _ in range(12):
        pairs.append((label(), answer(True, ["TABLE_NAME", "dynamodb:PutItem missing"])))
    for _ in range(12):
        pairs.append((label(), answer(True, ["memory", "timeout", "concurrency"])))
    for _ in range(6):
        pairs.append((label(), answer(False, layer="NONE", fn=None)))
    for _ in range(3):
        pairs.append((label(False), answer(True, ["something"])))
    for _ in range(27):
        pairs.append((label(False), answer(False, layer="NONE", fn=None)))
    return pairs


def test_table_f1_detection():
    c = confusion(table_f1_pairs())
    assert c == {"TP": 54, "FP": 3, "TN": 27, "FN": 6}
    m = detection_metrics(c)
    assert m["precision"] == pytest.approx(54 / 57)
    assert m["recall"] == pytest.approx(0.9)
    assert m["fpr"] == pytest.approx(0.1)


def test_table_f1_localisation():
    m = localisation_metrics(table_f1_pairs(), FUNCS)
    assert m["n_detected"] == 54
    assert m["top1"] == pytest.approx(30 / 54)
    assert m["top3"] == pytest.approx(42 / 54)


def test_level1_needs_layer_and_function():
    l = label()
    assert level1_correct(l, answer(True), FUNCS)
    assert not level1_correct(l, answer(True, layer="CONFIG"), FUNCS)
    assert not level1_correct(l, answer(True, fn="lambda-rca-bench-UploaderFunction-x"), FUNCS)
    assert level1_correct(l, answer(True, fn="crud-api"), FUNCS)


def test_level2_requires_function():
    l = label()
    assert not level2_hit_at_k(l, answer(True, ["dynamodb:PutItem"], fn="UploaderFunction"), 3, FUNCS)
    assert level2_hit_at_k(l, answer(True, ["role policy lacks dynamodb:PutItem"]), 1, FUNCS)


def test_cost_example():
    # Table F.1: 40,000 input and 1,500 output tokens
    pricing = {"input_per_million": 3.0, "output_per_million": 15.0}
    assert cost_usd(40_000, 1_500, pricing) == pytest.approx(0.12 + 0.0225)


def test_ttd():
    assert ttd_minutes("2026-10-11T10:00:00Z", "2026-10-11T10:03:00+00:00") == pytest.approx(3.0)
    assert math.isnan(ttd_minutes("2026-10-11T10:00:00Z", None))

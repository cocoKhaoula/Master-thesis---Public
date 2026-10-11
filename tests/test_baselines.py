from pathlib import Path

import numpy as np
import pandas as pd

from lambda_rca.baselines import cfn_drift, threshold
from lambda_rca.baselines.iforest import IForestBaseline
from lambda_rca.baselines.metrics import add_rates, intended_timeouts
from lambda_rca.config import Config

ROOT = Path(__file__).resolve().parents[1]
THR = {"error_rate": 0.05, "throttles": 1, "duration_fraction_of_timeout": 0.8,
       "datapoints_to_alarm": 2, "evaluation_periods": 3}


def frame(minutes, errors=0, throttles=0, start="2026-10-11T10:00:00Z", fn="crud-api", seed=0):
    rng = np.random.default_rng(seed)
    t = pd.date_range(start, periods=minutes, freq="1min")
    df = pd.DataFrame({"function": fn, "minute": t,
                       "invocations": 40 + rng.integers(-2, 3, minutes), "errors": errors, "throttles": throttles,
                       "duration_avg": 50 + rng.normal(0, 2, minutes), "duration_max": 120 + rng.normal(0, 5, minutes)})
    return add_rates(df.astype({"errors": float, "throttles": float}))


def test_intended_timeouts_from_template():
    cfg = Config.load()
    t = intended_timeouts(ROOT / "app" / "template.yaml", cfg.functions)
    assert t == {"crud-api": 10.0, "uploader": 30.0, "thumbnailer": 30.0, "compression": 60.0}


def test_threshold_alarm_after_two_breaching_minutes():
    df = frame(10)
    assert not threshold.detect(df, {"crud-api": 10}, THR)["anomaly"]
    df.loc[3:, "errors"] = 20
    df = add_rates(df)
    r = threshold.detect(df, {"crud-api": 10}, THR)
    assert r["anomaly"] and r["function"] == "crud-api"
    assert pd.Timestamp(r["detected_at"]) == pd.Timestamp("2026-10-11T10:05:00Z")


def test_iforest_flags_error_burst_not_normal():
    params = {"n_estimators": 100, "max_samples": 256, "contamination": "auto", "random_state": 42,
              "min_consecutive_minutes": 2}
    model = IForestBaseline(params).fit(frame(120, seed=1))
    assert not model.detect(frame(10, seed=2))["anomaly"]
    bad = frame(10, seed=3)
    bad.loc[2:, "errors"] = 35
    assert model.detect(add_rates(bad))["anomaly"]


def test_cfn_drift_prediction():
    cfg = Config.load()
    drift = {"finished": "2026-10-11T10:08:30Z", "drifted_resources": [{
        "logical_id": "CrudApiRole", "status": "MODIFIED",
        "differences": [{"path": "/Policies/0/PolicyDocument", "type": "NOT_EQUAL",
                         "expected": '{"Action":["dynamodb:PutItem","dynamodb:GetItem"]}',
                         "actual": '{"Action":["dynamodb:GetItem"]}'}]}]}
    p = cfn_drift.predict(drift, cfg.functions)
    assert p["anomaly"] and p["function"] == "crud-api" and p["root_cause_layer"] == "IAM"
    assert "PutItem" in p["candidates"][0]
    assert not cfn_drift.predict({"drifted_resources": []}, cfg.functions)["anomaly"]

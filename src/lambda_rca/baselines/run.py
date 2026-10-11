"""Apply all non-LLM baselines to the recorded windows (Section 3.7, "Baseline runs").

Output: data/baselines/<method>.jsonl with one prediction per window, in the same shape
as the agent answers, so that the evaluation treats every method identically.
"""
from __future__ import annotations

import logging

from ..aws import resolve_functions, session
from ..config import Config
from ..io import read_json, read_jsonl, write_jsonl
from . import cfn_drift, threshold
from .iforest import IForestBaseline
from .metrics import intended_timeouts, load_or_fetch

log = logging.getLogger(__name__)


def run_baselines(cfg: Config) -> None:
    cw = session(cfg, "harness").client("cloudwatch")
    functions = resolve_functions(cfg, "harness")
    metrics_dir = cfg.path("metrics_dir")
    out_dir = cfg.path("baselines_dir")
    windows = list(read_jsonl(cfg.path("windows_file")))
    timeouts = intended_timeouts(cfg.root / "app" / cfg["app"]["template_file"], cfg.functions)

    steady = read_json(cfg.path("data_dir") / "labels" / "steady_state.json")
    train = load_or_fetch(metrics_dir / "steady_state.csv", cw, functions, steady["start"], steady["end"])
    iforest = IForestBaseline(cfg["baselines"]["iforest"]).fit(train)

    thr_out, if_out, drift_out = [], [], []
    for w in windows:
        df = load_or_fetch(metrics_dir / f"{w['window_id']}.csv", cw, functions, w["start"], w["end"])

        t = threshold.detect(df, timeouts, cfg["baselines"]["threshold"])
        thr_out.append({"method": "threshold", "window_id": w["window_id"], "root_cause_layer": None,
                        "candidates": [], **t})

        i = iforest.detect(df)
        if_out.append({"method": "iforest", "window_id": w["window_id"], "root_cause_layer": None,
                       "candidates": [], **i})

        drift_file = out_dir / "cfn_drift" / f"{w['window_id']}.json"
        d = cfn_drift.predict(read_json(drift_file), cfg.functions) if drift_file.exists() else \
            {"anomaly": False, "function": None, "root_cause_layer": "NONE", "candidates": [],
             "detected_at": None, "error": "no drift record"}
        drift_out.append({"method": "cfn_drift", "window_id": w["window_id"], **d})

    write_jsonl(out_dir / "threshold.jsonl", thr_out)
    write_jsonl(out_dir / "iforest.jsonl", if_out)
    write_jsonl(out_dir / "cfn_drift.jsonl", drift_out)
    log.info("baselines written for %d windows", len(windows))

"""CloudWatch metrics per function and minute (Section 2.3), used by the threshold and
Isolation Forest baselines. Fetched once per window and cached as CSV in data/metrics/."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ..aws import FunctionResources
from ..io import parse_iso

METRICS = [
    ("Invocations", "Sum", "invocations"),
    ("Errors", "Sum", "errors"),
    ("Throttles", "Sum", "throttles"),
    ("Duration", "Average", "duration_avg"),
    ("Duration", "Maximum", "duration_max"),
]
FEATURES = ["invocations", "errors", "error_rate", "throttles", "throttle_rate", "duration_avg", "duration_max"]


def fetch_metrics(cw, functions: dict[str, FunctionResources], start_iso: str, end_iso: str) -> pd.DataFrame:
    """One row per (function, minute) with the raw metrics and derived rates."""
    queries, ids = [], {}
    for fi, (key, fn) in enumerate(functions.items()):
        for mi, (metric, stat, col) in enumerate(METRICS):
            qid = f"m{fi}_{mi}"
            ids[qid] = (key, col)
            queries.append({
                "Id": qid,
                "MetricStat": {"Metric": {"Namespace": "AWS/Lambda", "MetricName": metric,
                                          "Dimensions": [{"Name": "FunctionName", "Value": fn.function_name}]},
                               "Period": 60, "Stat": stat},
                "ReturnData": True,
            })
    start, end = parse_iso(start_iso), parse_iso(end_iso)
    rows: dict[tuple[str, pd.Timestamp], dict] = {}
    paginator = cw.get_paginator("get_metric_data")
    for page in paginator.paginate(MetricDataQueries=queries, StartTime=start, EndTime=end, ScanBy="TimestampAscending"):
        for res in page["MetricDataResults"]:
            key, col = ids[res["Id"]]
            for ts, v in zip(res["Timestamps"], res["Values"]):
                rows.setdefault((key, pd.Timestamp(ts)), {})[col] = v

    # complete grid: minutes without datapoints mean no invocations
    minutes = pd.date_range(pd.Timestamp(start).floor("min"), pd.Timestamp(end).floor("min"),
                            freq="1min", inclusive="left")
    records = []
    for key in functions:
        for m in minutes:
            r = rows.get((key, m), {})
            records.append({"function": key, "minute": m, **{c: r.get(c, 0.0) for _, _, c in METRICS}})
    df = pd.DataFrame.from_records(records)
    return add_rates(df)


def add_rates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    attempts = df["invocations"] + df["throttles"]
    df["error_rate"] = (df["errors"] / df["invocations"].where(df["invocations"] > 0)).fillna(0.0)
    df["throttle_rate"] = (df["throttles"] / attempts.where(attempts > 0)).fillna(0.0)
    return df


def load_or_fetch(path: Path, cw, functions, start_iso: str, end_iso: str) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, parse_dates=["minute"])
        return df
    df = fetch_metrics(cw, functions, start_iso, end_iso)
    # cache only complete windows: CloudWatch needs a few minutes for the last data points
    from ..io import utcnow
    if (utcnow() - parse_iso(end_iso)).total_seconds() > 15 * 60:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
    return df


class _IgnoreTagsLoader(yaml.SafeLoader):
    pass


_IgnoreTagsLoader.add_multi_constructor("!", lambda loader, suffix, node: None)


def intended_timeouts(template_path: Path, functions_cfg: dict) -> dict[str, float]:
    """Timeout (seconds) of every function in the intended state (SAM template)."""
    tpl = yaml.load(template_path.read_text(encoding="utf-8"), Loader=_IgnoreTagsLoader)
    default = (tpl.get("Globals", {}).get("Function", {}) or {}).get("Timeout", 3)
    out = {}
    for key, f in functions_cfg.items():
        props = tpl["Resources"][f["logical_id"]]["Properties"]
        out[key] = float(props.get("Timeout", default))
    return out

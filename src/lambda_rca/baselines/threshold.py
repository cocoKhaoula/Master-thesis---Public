"""Static threshold alarms (Section 6.1): the common-practice baseline.

Evaluated offline on the per-minute metrics with the same semantics as a CloudWatch
alarm with period 60 s and "M out of N" datapoints, so that the rules are applied
identically to every window and are reproducible.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def breaching(df: pd.DataFrame, timeouts: dict[str, float], p: dict[str, Any]) -> pd.Series:
    limit_ms = df["function"].map(timeouts) * 1000 * p["duration_fraction_of_timeout"]
    return ((df["error_rate"] > p["error_rate"])
            | (df["throttles"] >= p["throttles"])
            | (df["duration_max"] > limit_ms))


def detect(df: pd.DataFrame, timeouts: dict[str, float], p: dict[str, Any]) -> dict[str, Any]:
    """Return the window prediction and the time of the first alarm."""
    df = df.sort_values(["function", "minute"]).copy()
    df["breach"] = breaching(df, timeouts, p)
    m, n = p["datapoints_to_alarm"], p["evaluation_periods"]
    first: tuple[pd.Timestamp, str] | None = None
    breaches_per_fn = {}
    for fn, g in df.groupby("function"):
        roll = g["breach"].astype(int).rolling(n, min_periods=1).sum()
        alarm = g.loc[roll >= m, "minute"]
        breaches_per_fn[fn] = int(g["breach"].sum())
        if not alarm.empty:
            # the datapoint for minute t is complete at t + 1 min
            t = alarm.iloc[0] + pd.Timedelta(minutes=1)
            if first is None or t < first[0]:
                first = (t, fn)
    if first is None:
        return {"anomaly": False, "function": None, "detected_at": None}
    return {"anomaly": True, "function": first[1], "detected_at": first[0].isoformat(),
            "breaches": breaches_per_fn}

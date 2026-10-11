"""Isolation Forest baseline (Section 6.1; Liu, Ting and Zhou, 2008).

One model per function, trained only on the steady-state period recorded before the
injection campaign, so that no evaluation window enters the training data. A minute is
flagged if the model predicts it as an outlier; a window is anomalous if some function
has at least `min_consecutive_minutes` consecutive flagged minutes.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .metrics import FEATURES

JITTER = 1e-3


class IForestBaseline:
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self.models: dict[str, IsolationForest] = {}

    def fit(self, train: pd.DataFrame) -> "IForestBaseline":
        rng = np.random.default_rng(self.params["random_state"])
        self.constant_features: dict[str, list[str]] = {}
        for fn, g in train.groupby("function"):
            X = g[FEATURES].to_numpy(dtype=float)
            # In steady state errors and throttles are always 0. The trees never split on a
            # constant feature, so deviations in it would be invisible to the model. A
            # negligible jitter makes the feature splittable; values outside the training
            # range are then isolated quickly.
            const = X.std(axis=0) == 0
            X[:, const] += rng.normal(0.0, JITTER, size=(len(X), int(const.sum())))
            self.constant_features[fn] = [f for f, c in zip(FEATURES, const) if c]
            model = IsolationForest(n_estimators=self.params["n_estimators"],
                                    max_samples=min(self.params["max_samples"], len(g)),
                                    contamination=self.params["contamination"],
                                    random_state=self.params["random_state"])
            model.fit(X)
            self.models[fn] = model
        return self

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.sort_values(["function", "minute"]).copy()
        df["score"] = 0.0
        df["flag"] = False
        for fn, idx in df.groupby("function").groups.items():
            model = self.models[fn]
            X = df.loc[idx, FEATURES].to_numpy()
            # sklearn's score_samples is the negated anomaly score s(x, n) of eq. 6.1
            df.loc[idx, "score"] = -model.score_samples(X)
            df.loc[idx, "flag"] = model.predict(X) == -1
        return df

    def detect(self, df: pd.DataFrame) -> dict[str, Any]:
        scored = self.score(df)
        k = self.params["min_consecutive_minutes"]
        first = None
        for fn, g in scored.groupby("function"):
            run = 0
            for minute, flag in zip(g["minute"], g["flag"]):
                run = run + 1 if flag else 0
                if run >= k:
                    t = minute + pd.Timedelta(minutes=1)
                    if first is None or t < first[0]:
                        first = (t, fn)
                    break
        max_scores = scored.groupby("function")["score"].max().round(4).to_dict()
        if first is None:
            return {"anomaly": False, "function": None, "detected_at": None, "max_score": max_scores}
        return {"anomaly": True, "function": first[1], "detected_at": first[0].isoformat(), "max_score": max_scores}

"""Join all outputs with the labels on the window identifier and compute the metrics of
Section 2.6 per method, ablation level, repetition and fault type (Section 3.7, step 6).

Writes CSV and Markdown tables to results/ (inputs for Chapter 7 and Table 6.1).
Agent metrics are computed per repetition and reported as mean and standard deviation
across repetitions (Section 2.5).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import Config
from ..io import read_json, read_jsonl
from .metrics import (confusion, cost_usd, detection_metrics, localisation_metrics, ttd_minutes)

log = logging.getLogger(__name__)

BASELINES = ["threshold", "iforest", "cfn_drift"]
RUN_FILE = re.compile(r"^(W\d+)_r(\d+)\.json$")
TTD_FILE = re.compile(r"^(W\d+)_ttd(\d+)_r1\.json$")


# ------------------------------------------------------------------ loading
def load_labels(cfg: Config) -> dict[str, dict]:
    return {l["incident_id"]: l for l in read_jsonl(cfg.path("labels_file"))}


def load_predictions(cfg: Config) -> pd.DataFrame:
    rows = []
    runs_dir = cfg.path("runs_dir")
    for level_dir in sorted(p for p in runs_dir.glob("L*") if p.is_dir()):
        for f in sorted(level_dir.glob("*.json")):
            m = RUN_FILE.match(f.name)
            if not m:
                continue
            r = read_json(f)
            a = r["answer"]
            rows.append({
                "method": f"agent-{level_dir.name}", "level": level_dir.name, "rep": int(m.group(2)),
                "window_id": m.group(1), "anomaly": bool(a["anomaly"]), "function": a.get("function"),
                "root_cause_layer": a.get("root_cause_layer"), "candidates": a.get("candidates", []),
                "detected_at": None, "valid": r["valid"],
                "input_tokens": r["usage"]["input_tokens"], "output_tokens": r["usage"]["output_tokens"],
                "cache_read_tokens": r["usage"].get("cache_read_input_tokens", 0),
                "cache_write_tokens": r["usage"].get("cache_write_input_tokens", 0),
                "latency_s": r["latency_s"], "n_tool_calls": len(r["tool_calls"]),
            })
    for b in BASELINES:
        for r in read_jsonl(cfg.path("baselines_dir") / f"{b}.jsonl"):
            rows.append({
                "method": b, "level": None, "rep": 1, "window_id": r["window_id"],
                "anomaly": bool(r["anomaly"]), "function": r.get("function"),
                "root_cause_layer": r.get("root_cause_layer"), "candidates": r.get("candidates", []),
                "detected_at": r.get("detected_at"), "valid": True,
                "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0,
                "latency_s": np.nan, "n_tool_calls": 0,
            })
    return pd.DataFrame(rows)


def load_agent_ttd(cfg: Config, labels: dict[str, dict]) -> pd.DataFrame:
    """Agent TTD from polling runs: first prefix length at which an anomaly is reported."""
    rows = []
    for level_dir in sorted(p for p in cfg.path("runs_dir").glob("L*") if p.is_dir()):
        first: dict[str, float] = {}
        for f in sorted(level_dir.glob("*_ttd*_r1.json")):
            m = TTD_FILE.match(f.name)
            if not m:
                continue
            wid, minutes = m.group(1), int(m.group(2))
            if read_json(f)["answer"]["anomaly"]:
                first[wid] = min(first.get(wid, np.inf), minutes)
        for wid, minutes in first.items():
            if wid in labels and labels[wid]["symptomatic"]:
                rows.append({"method": f"agent-{level_dir.name}", "window_id": wid, "ttd_min": minutes,
                             "fault_type": labels[wid]["fault_type"]})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ aggregation
def _per_rep(preds: pd.DataFrame, labels: dict[str, dict], cfg: Config, fault_type: str | None = None) -> pd.DataFrame:
    rows = []
    for (method, rep), g in preds.groupby(["method", "rep"], dropna=False):
        pairs = [(labels[w], p) for w, p in zip(g["window_id"], g.to_dict("records")) if w in labels]
        if fault_type:
            pairs = [(l, p) for l, p in pairs if l["fault_type"] == fault_type]
        if not pairs:
            continue
        c = confusion(pairs)
        row = {"method": method, "rep": rep, "n_windows": len(pairs), **c, **detection_metrics(c),
               **localisation_metrics(pairs, cfg.functions)}
        # tokens processed by the model = uncached + cache-write + cache-read input + output
        tok = lambda p: p["input_tokens"] + p["cache_read_tokens"] + p["cache_write_tokens"] + p["output_tokens"]
        row["tokens_per_window"] = sum(tok(p) for _, p in pairs) / len(pairs)
        sym = [(l, p) for l, p in pairs if l["symptomatic"]]
        row["tokens_per_incident"] = sum(tok(p) for _, p in sym) / len(sym) if sym else np.nan
        row["cost_per_window_usd"] = sum(
            cost_usd(p["input_tokens"], p["output_tokens"], cfg["pricing"], p["cache_read_tokens"], p["cache_write_tokens"])
            for _, p in pairs) / len(pairs)
        row["invalid_rate"] = 1 - sum(p["valid"] for _, p in pairs) / len(pairs)
        rows.append(row)
    return pd.DataFrame(rows)


def _mean_std(per_rep: pd.DataFrame) -> pd.DataFrame:
    if per_rep.empty:
        return per_rep
    num = per_rep.drop(columns=["rep"]).groupby("method")
    mean = num.mean(numeric_only=True)
    std = num.std(numeric_only=True).fillna(0.0)
    out = mean.copy()
    for col in ["precision", "recall", "fpr", "f1", "level1", "top1", "top3"]:
        if col in out:
            out[f"{col}_std"] = std[col]
    out["reps"] = per_rep.groupby("method")["rep"].nunique()
    return out.reset_index()


def _order(df: pd.DataFrame) -> pd.DataFrame:
    order = BASELINES + [f"agent-L{i}" for i in range(5)]
    df = df.copy()
    df["_o"] = df["method"].map({m: i for i, m in enumerate(order)}).fillna(99)
    return df.sort_values("_o").drop(columns="_o")


def evaluate(cfg: Config) -> dict[str, pd.DataFrame]:
    labels = load_labels(cfg)
    preds = load_predictions(cfg)
    if preds.empty:
        raise SystemExit("no predictions found - run the agent and baselines first")
    out_dir = cfg.path("results_dir")
    out_dir.mkdir(parents=True, exist_ok=True)

    per_rep = _per_rep(preds, labels, cfg)
    summary = _order(_mean_std(per_rep))

    # per fault type (Section 7.4)
    by_fault = []
    for ft in sorted({l["fault_type"] for l in labels.values()}):
        s = _mean_std(_per_rep(preds, labels, cfg, ft))
        if not s.empty:
            s.insert(1, "fault_type", ft)
            by_fault.append(s)
    by_fault_df = _order(pd.concat(by_fault)) if by_fault else pd.DataFrame()

    # time to detect (Section 7.5)
    ttd_rows = []
    base = preds[preds["method"].isin(BASELINES) & preds["anomaly"]]
    for r in base.to_dict("records"):
        l = labels.get(r["window_id"])
        if l and l["symptomatic"]:
            ttd_rows.append({"method": r["method"], "window_id": r["window_id"], "fault_type": l["fault_type"],
                             "ttd_min": ttd_minutes(l["start_time"], r["detected_at"])})
    ttd = pd.concat([pd.DataFrame(ttd_rows), load_agent_ttd(cfg, labels)], ignore_index=True)
    ttd_summary = (ttd.groupby("method")["ttd_min"]
                   .agg(median="median", q1=lambda s: s.quantile(0.25), q3=lambda s: s.quantile(0.75), n="count")
                   .reset_index() if not ttd.empty else pd.DataFrame())

    # cost per level and marginal cost of each layer (Section 7.6, Appendix F)
    agent = summary[summary["method"].str.startswith("agent-")].copy()
    if not agent.empty:
        agent["marginal_tokens"] = agent["tokens_per_window"].diff()
        agent["marginal_top3"] = agent["top3"].diff()
    cost = agent[["method", "tokens_per_window", "tokens_per_incident", "cost_per_window_usd",
                  "marginal_tokens", "top3", "marginal_top3", "recall"]] if not agent.empty else agent

    tables = {"summary": summary, "per_repetition": per_rep, "by_fault_type": by_fault_df,
              "ttd": ttd, "ttd_summary": ttd_summary, "cost": cost}
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
    write_markdown(out_dir / "results.md", tables, cfg)
    log.info("results written to %s", out_dir)
    return tables


def _fmt(v, std=None) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    s = f"{v:.3f}"
    if std is not None and not np.isnan(std) and std > 0:
        s += f" ± {std:.3f}"
    return s


def write_markdown(path: Path, tables: dict[str, pd.DataFrame], cfg: Config) -> None:
    s = tables["summary"]
    lines = ["# Results", "",
             f"Price date for cost: {cfg['pricing']['price_date']} "
             f"(input ${cfg['pricing']['input_per_million']}/M, output ${cfg['pricing']['output_per_million']}/M tokens).",
             "", "## Table 6.1 - comparison with baselines", "",
             "| Method | Precision | Recall | FPR | Level-1 | Top-1 | Top-3 | Tokens/window | Cost/window (USD) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in s.to_dict("records"):
        rca = r["method"] not in ("threshold", "iforest")
        lines.append("| {m} | {p} | {rc} | {f} | {l1} | {t1} | {t3} | {tok} | {c} |".format(
            m=r["method"], p=_fmt(r["precision"], r.get("precision_std")), rc=_fmt(r["recall"], r.get("recall_std")),
            f=_fmt(r["fpr"], r.get("fpr_std")),
            l1=_fmt(r["level1"], r.get("level1_std")) if rca else "n/a",
            t1=_fmt(r["top1"], r.get("top1_std")) if rca else "n/a",
            t3=_fmt(r["top3"], r.get("top3_std")) if rca else "n/a",
            tok=f"{r['tokens_per_window']:.0f}", c=f"{r['cost_per_window_usd']:.4f}"))
    lines += ["", "Values are mean ± standard deviation across repetitions; localisation is computed on detected "
              "symptomatic incidents only (Section 2.6).", ""]
    if not tables["ttd_summary"].empty:
        lines += ["## Time to detect (minutes)", "", "| Method | Median | Q1 | Q3 | n |", "|---|---|---|---|---|"]
        for r in tables["ttd_summary"].to_dict("records"):
            lines.append(f"| {r['method']} | {_fmt(r['median'])} | {_fmt(r['q1'])} | {_fmt(r['q3'])} | {r['n']} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")

"""Figures for Chapter 7, drawn from the CSV tables in results/."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from ..config import Config  # noqa: E402

BLUE, ORANGE, GREY = "#2a6fdb", "#e07b39", "#8a8a8a"


def _agent(summary: pd.DataFrame) -> pd.DataFrame:
    a = summary[summary["method"].str.startswith("agent-")].copy()
    a["level"] = a["method"].str.replace("agent-", "", regex=False)
    return a


def plot_all(cfg: Config) -> None:
    out = cfg.path("results_dir")
    summary = pd.read_csv(out / "summary.csv")
    agent = _agent(summary)

    # Detection per ablation level (RQ1)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for col, color, label in [("precision", BLUE, "Precision"), ("recall", ORANGE, "Recall"), ("fpr", GREY, "FPR")]:
        ax.errorbar(agent["level"], agent[col], yerr=agent.get(f"{col}_std"), marker="o", color=color,
                    label=label, capsize=3)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Ablation level")
    ax.set_title("Detection by ablation level")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "fig_detection_by_level.png", dpi=200)
    plt.close(fig)

    # Root-cause localisation per level (RQ2)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for col, color, label in [("level1", GREY, "Level 1 (layer + function)"),
                              ("top1", BLUE, "Level 2 top-1"), ("top3", ORANGE, "Level 2 top-3")]:
        ax.errorbar(agent["level"], agent[col], yerr=agent.get(f"{col}_std"), marker="o", color=color,
                    label=label, capsize=3)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Ablation level")
    ax.set_title("Root-cause localisation by ablation level")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "fig_rca_by_level.png", dpi=200)
    plt.close(fig)

    # Cost-accuracy (RQ3)
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot(agent["tokens_per_window"], agent["top3"], marker="o", color=BLUE)
    for r in agent.to_dict("records"):
        ax.annotate(r["level"], (r["tokens_per_window"], r["top3"]), textcoords="offset points", xytext=(5, 5))
    ax.set_xlabel("Mean tokens per window")
    ax.set_ylabel("Top-3 accuracy (Level 2)")
    ax.set_title("Cost-accuracy trade-off")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "fig_cost_accuracy.png", dpi=200)
    plt.close(fig)

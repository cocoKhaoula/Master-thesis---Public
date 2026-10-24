"""Figures for the thesis report and presentation (process diagrams + result charts).

Run from the project folder after `lambda-rca evaluate`:
    .venv\\Scripts\\python scripts\\make_figures.py
Writes PNG files (200 dpi) to results/figures/.
"""
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = RES / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# validated categorical palette (light surface) + text tokens
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GREY, INK, INK2, GRID, SURF = "#8a8986", "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": GREY, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 12, "axes.titleweight": "bold",
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.dpi": 200,
})
LEVELS = ["L0", "L1", "L2", "L3", "L4"]
LEVEL_NAMES = {"L0": "L0\nraw logs", "L1": "L1\n+telemetry", "L2": "L2\n+IAM", "L3": "L3\n+IaC & live cfg",
               "L4": "L4\n+code history"}


def clean(ax, ygrid=True):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if ygrid:
        ax.yaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)


def box(ax, x, y, w, h, text, fc, ec, fs=9, bold=False, tc=INK):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1.4))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=tc,
            fontweight="bold" if bold else "normal", wrap=True)


def arrow(ax, x1, y1, x2, y2, text=None, color=INK2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4, shrinkA=2, shrinkB=2))
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, text, ha="center", va="bottom", fontsize=7.5, color=INK2)


# ------------------------------------------------------------------ 1. experiment pipeline
def fig_pipeline():
    fig, ax = plt.subplots(figsize=(13, 6.2))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6.2)
    ax.axis("off")
    lb, lo, lg, lp = "#e8f1fb", "#fdeee6", "#e6f6ef", "#f1eefb"
    # row 1: set-up
    box(ax, 0.2, 4.6, 2.4, 1.2, "1. Benchmark app\nAWS SAM, eu-north-1\n4 SeBS Lambda functions\nS3 + DynamoDB", lb, BLUE)
    box(ax, 3.0, 4.6, 2.4, 1.2, "2. Load generator\n40 req/min per function\nbursts of 2 concurrent", lb, BLUE)
    box(ax, 5.8, 4.6, 2.4, 1.2, "3. Steady state (30 min)\nfault-free telemetry\n→ Isolation Forest training", lb, BLUE)
    box(ax, 8.6, 4.6, 4.2, 1.2, "4. Window plan: 95 windows\n60 faults (F1–F5) · 15 silent drift (F6) · 20 normal\nneutral IDs W001–W095, seeded order", lb, BLUE)
    arrow(ax, 2.6, 5.2, 3.0, 5.2)
    arrow(ax, 5.4, 5.2, 5.8, 5.2)
    arrow(ax, 8.2, 5.2, 8.6, 5.2)
    # row 2: per-window loop
    ax.add_patch(FancyBboxPatch((0.1, 1.55), 12.8, 2.65, boxstyle="round,pad=0.02,rounding_size=0.12",
                                fc="none", ec=GREY, lw=1.2, ls="--"))
    ax.text(0.3, 3.98, "Repeated for every window (≈ 27 min each)", fontsize=9, color=INK2, fontweight="bold")
    box(ax, 0.3, 2.0, 1.9, 1.6, "5. Load check\nall functions get\n≥ 60 % of the\nexpected traffic", lo, ORANGE)
    box(ax, 2.5, 2.0, 2.0, 1.6, "6. Inject fault\nsave original state\nF1 IAM · F2 mem/timeout\nF3 env var · F4 throttle\nF5 commit · F6 silent", lo, ORANGE)
    box(ax, 4.8, 2.0, 2.0, 1.6, "7. 10-min window\nCloudWatch metrics/logs\ndrift check at min 8\nconfig snapshot", lo, ORANGE)
    box(ax, 7.1, 2.0, 2.6, 1.6, "8. LLM agent (fault active)\nClaude Haiku 5.5, ReAct\nL0 raw logs → L4 +code\nread-only AWS role\nJSON answer + tokens", lp, "#6250d6")
    box(ax, 10.0, 2.0, 2.8, 1.6, "9. Revert + label\nexact restore (retried)\nlabel: fault, function,\nlayer, artefact\n10-min recovery", lo, ORANGE)
    for x1, x2 in ((2.2, 2.5), (4.5, 4.8), (6.8, 7.1), (9.7, 10.0)):
        arrow(ax, x1, 2.8, x2, 2.8)
    arrow(ax, 10.7, 4.6, 10.7, 4.2)
    # row 3: analysis
    box(ax, 0.3, 0.15, 3.6, 1.0, "10. Baselines on the same windows\nthreshold alarms · Isolation Forest\nCloudFormation drift detection", lg, AQUA)
    box(ax, 4.3, 0.15, 3.6, 1.0, "11. Evaluation\nprecision · recall · FPR · Level-1/2 top-k\ntime to detect · tokens & cost", lg, AQUA)
    box(ax, 8.3, 0.15, 4.5, 1.0, "12. Results (Chapter 7)\n92 labelled windows · 460 agent runs\ntables, figures, GitHub dataset", lg, AQUA)
    # after the last window: elbow from step 9 to step 10, then left to right
    ax.plot([11.4, 11.4, 2.1], [2.0, 1.35, 1.35], color=INK2, lw=1.4)
    arrow(ax, 2.1, 1.35, 2.1, 1.15)
    arrow(ax, 3.9, 0.65, 4.3, 0.65)
    arrow(ax, 7.9, 0.65, 8.3, 0.65)
    ax.set_title("How the experiment was performed - from deployment to results", loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_experiment_pipeline.png")
    plt.close(fig)


# ------------------------------------------------------------------ 2. one injection cycle (timeline)
def fig_cycle():
    fig, ax = plt.subplots(figsize=(12, 3.2))
    segs = [("load\ncheck", 2, "#f3f2ef", GREY), ("fault active - 10-min labelled window", 10, "#fdeee6", ORANGE),
            ("+2\nmin", 2, "#f3f2ef", GREY), ("agent L0-L4\n(fault still active)", 6, "#f1eefb", "#6250d6"),
            ("revert", 1.2, "#fdeee6", ORANGE), ("recovery - 10 min", 10, "#e8f1fb", BLUE)]
    x = 0
    for label, w, fc, ec in segs:
        ax.add_patch(FancyBboxPatch((x, 0.4), w - 0.15, 0.9, boxstyle="round,pad=0,rounding_size=0.15", fc=fc, ec=ec, lw=1.4))
        ax.text(x + w / 2, 0.85, label, ha="center", va="center", fontsize=8.5, color=INK)
        x += w
    ax.annotate("drift check\n(minute 8)", xy=(2 + 8, 1.3), xytext=(2 + 8, 1.95), ha="center", fontsize=8, color=INK2,
                arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1))
    ax.annotate("inject", xy=(2, 1.3), xytext=(2, 1.95), ha="center", fontsize=8, color=INK2,
                arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1))
    ax.annotate("snapshot +\nload check", xy=(14, 1.3), xytext=(14.4, 1.95), ha="center", fontsize=8, color=INK2,
                arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1))
    ax.set_xlim(-0.3, x + 0.3)
    ax.set_ylim(0, 2.5)
    ax.set_yticks([])
    ax.set_xticks([0, 2, 12, 14, 20, 21.2, 31.2])
    ax.set_xticklabels(["0", "2", "12", "14", "≈20", "≈21", "≈31 min"])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.set_title("One injection cycle (per window)", loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_injection_cycle.png")
    plt.close(fig)


# ------------------------------------------------------------------ 3. dataset composition
def fig_dataset():
    labels = [json.loads(l) for l in open(ROOT / "data/labels/labels.jsonl", encoding="utf8")]
    c = Counter(l["fault_type"] for l in labels)
    names = {"F1": "F1 remove IAM permission", "F2": "F2 lower memory/timeout", "F3": "F3 wrong env variable",
             "F4": "F4 throttling (concurrency)", "F5": "F5 faulty committed change", "F6": "F6 silent drift (negative)",
             "N": "Normal window (negative)"}
    order = ["F1", "F2", "F3", "F4", "F5", "F6", "N"]
    vals = [c[k] for k in order]
    colors = [ORANGE] * 5 + [GREY, GREY]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    y = np.arange(len(order))[::-1]
    ax.barh(y, vals, color=colors, height=0.62)
    for yi, v in zip(y, vals):
        ax.text(v + 0.3, yi, str(v), va="center", fontsize=9, color=INK)
    ax.set_yticks(y)
    ax.set_yticklabels([names[k] for k in order])
    ax.set_xlabel("labelled windows")
    ax.set_xlim(0, max(vals) + 3)
    clean(ax, ygrid=False)
    ax.xaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)
    ax.set_title(f"Dataset: {len(labels)} labelled windows (57 symptomatic, 35 negative)", loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_dataset.png")
    plt.close(fig)


# ------------------------------------------------------------------ result charts
def agent_rows(s):
    a = s[s["method"].str.startswith("agent-")].copy()
    a["level"] = a["method"].str.replace("agent-", "", regex=False)
    return a.set_index("level").loc[LEVELS]


def line_chart(a, cols, title, fname, ylabel):
    """Grouped bars per ablation level (levels are categories, so bars avoid label overlap)."""
    fig, ax = plt.subplots(figsize=(9, 4.4))
    x = np.arange(len(LEVELS))
    w = 0.8 / len(cols)
    for k, (col, color, label, _mk) in enumerate(cols):
        v = a[col].values.astype(float)
        bars = ax.bar(x + (k - (len(cols) - 1) / 2) * w, v, w - 0.03, color=color, label=label)
        for b, vi in zip(bars, v):
            ax.text(b.get_x() + b.get_width() / 2, vi + 0.015, f"{vi:.2f}", ha="center", fontsize=7.5, color=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels([LEVEL_NAMES[l] for l in LEVELS], fontsize=8.5)
    ax.set_ylim(0, 1.18)
    ax.set_ylabel(ylabel)
    clean(ax)
    ax.legend(frameon=False, loc="upper left", ncol=len(cols), fontsize=8.5)
    ax.set_title(title, loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / fname)
    plt.close(fig)


def fig_heatmap(bf):
    faults = ["F1", "F2", "F3", "F4", "F5"]
    ag = bf[bf["method"].str.startswith("agent-")].copy()
    ag["level"] = ag["method"].str.replace("agent-", "", regex=False)
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for ax, col, title in ((axes[0], "recall", "Detection recall"), (axes[1], "top3", "Root cause found (Level-2 top-3)")):
        m = np.full((len(faults), len(LEVELS)), np.nan)
        for i, f in enumerate(faults):
            for j, l in enumerate(LEVELS):
                r = ag[(ag["fault_type"] == f) & (ag["level"] == l)]
                if len(r) and not pd.isna(r[col].iloc[0]):
                    m[i, j] = r[col].iloc[0]
        ax.imshow(np.nan_to_num(m, nan=0), cmap="Blues", vmin=0, vmax=1, aspect="auto")
        for i in range(len(faults)):
            for j in range(len(LEVELS)):
                v = m[i, j]
                txt = "–" if np.isnan(v) else f"{v:.2f}"
                ax.text(j, i, txt, ha="center", va="center", fontsize=9,
                        color="white" if (not np.isnan(v) and v > 0.6) else INK)
        ax.set_xticks(range(len(LEVELS)))
        ax.set_xticklabels(LEVELS)
        ax.set_yticks(range(len(faults)))
        ax.set_yticklabels(["F1 IAM", "F2 mem/timeout", "F3 env var", "F4 throttling", "F5 commit"])
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        for s in ax.spines.values():
            s.set_visible(False)
    fig.suptitle("Agent results by fault type and ablation level ('–' = not detected, so no root cause to rank)",
                 x=0.01, ha="left", fontsize=10, color=INK2)
    fig.tight_layout()
    fig.savefig(OUT / "fig_fault_type_heatmap.png")
    plt.close(fig)


def fig_cost(a):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    tok = a["tokens_per_window"].values / 1000
    acc = a["top3"].values
    ax.plot(tok, acc, color=GRID, lw=1, zorder=1)
    ax.scatter(tok, acc, s=90, color=BLUE, edgecolor="white", linewidth=1.5, zorder=2)
    for l, t, v, c in zip(LEVELS, tok, acc, a["cost_per_window_usd"].values):
        ax.annotate(f"{l}  ${c:.4f}", (t, v), textcoords="offset points", xytext=(8, -4), fontsize=9, color=INK)
    ax.set_xlabel("mean tokens per window (thousands, incl. cached input)")
    ax.set_ylabel("root cause found (top-3)")
    ax.set_ylim(0.5, 1.07)
    ax.set_xlim(0, max(tok) * 1.25)
    clean(ax)
    ax.set_title("Cost vs. accuracy per ablation level (Claude Haiku 5.5, 1 run per window)", loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_cost_accuracy.png")
    plt.close(fig)


def fig_baselines(s):
    order = ["threshold", "iforest", "cfn_drift", "agent-L1", "agent-L4"]
    names = ["Threshold\nalarms", "Isolation\nForest", "CloudFormation\ndrift", "Agent L1\n(telemetry)", "Agent L4\n(full context)"]
    d = s.set_index("method").loc[order]
    x = np.arange(len(order))
    w = 0.26
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for k, (col, color, label) in enumerate((("recall", BLUE, "Recall"), ("fpr", ORANGE, "False-positive rate"),
                                             ("top3", AQUA, "Root cause top-3"))):
        vals = d[col].values.astype(float)
        if col == "top3":
            vals = np.where([m in ("threshold", "iforest") for m in order], np.nan, vals)
        bars = ax.bar(x + (k - 1) * w, np.nan_to_num(vals), w - 0.03, color=color, label=label)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, (0 if np.isnan(v) else v) + 0.02,
                    "n/a" if np.isnan(v) else f"{v:.2f}", ha="center", fontsize=7.5, color=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=8.5)
    ax.set_ylim(0, 1.15)
    clean(ax)
    ax.legend(frameon=False, ncol=3, loc="upper left", fontsize=9)
    ax.set_title("Agent vs. baselines on the same 92 windows", loc="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "fig_baselines.png")
    plt.close(fig)


if __name__ == "__main__":
    s = pd.read_csv(RES / "summary.csv")
    bf = pd.read_csv(RES / "by_fault_type.csv")
    a = agent_rows(s)
    fig_pipeline()
    fig_cycle()
    fig_dataset()
    line_chart(a, [("precision", BLUE, "Precision", "o"), ("recall", ORANGE, "Recall", "s"),
                   ("fpr", GREY, "False-positive rate", "^")],
               "Detection by ablation level (RQ1)", "fig_detection_by_level.png", "score")
    line_chart(a, [("level1", GREY, "Level 1: correct layer + function", "^"), ("top1", BLUE, "Level 2: exact artefact, top-1", "o"),
                   ("top3", ORANGE, "Level 2: exact artefact, top-3", "s")],
               "Root-cause localisation by ablation level (RQ2)", "fig_rca_by_level.png", "accuracy (detected incidents)")
    fig_heatmap(bf)
    fig_cost(a)
    fig_baselines(s)
    print("figures written to", OUT)
    for p in sorted(OUT.glob("*.png")):
        print(" ", p.name)

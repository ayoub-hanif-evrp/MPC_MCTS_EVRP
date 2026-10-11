"""Measured, CSV-backed screening figures. Never render unexecuted studies."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .storage import writable_path

ORDER = ["GREEDY", "RH_REGRET", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS", "MPC_MCTS_H1"]
LABELS = dict(zip(ORDER, ["Greedy", "RH regret", "Independent MPC-MCTS", "Coordinated MPC-MCTS", "MPC-MCTS H1"]))
COLORS = dict(zip(ORDER, ["#727272", "#cc7933", "#24865b", "#316caa", "#994c87"]))


def save_figure(fig, data, stem):
    stem = Path(stem)
    data.to_csv(writable_path(stem.with_name(stem.name + "_data.csv")), index=False)
    fig.tight_layout()
    destination = writable_path(stem.with_suffix(".png"))
    fig.savefig(destination, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(destination)


def _panel(ax, data, x, metric):
    for algorithm in ORDER:
        group = data[(data.algorithm == algorithm) & (data.metric == metric)].sort_values(x)
        if group.empty:
            continue
        if group.duplicated(x).any():
            raise ValueError("Multiple configurations at one figure point; aggregate one study/configuration at a time")
        positions = group[x].astype(str)
        ax.plot(positions, group["mean"], marker="o", color=COLORS[algorithm],
                linestyle="-" if len(group) > 1 else "none", label=LABELS[algorithm])
        for position, (_, row) in zip(positions, group.iterrows()):
            if pd.notna(row.ci95_low) and pd.notna(row.ci95_high):
                ax.vlines(position, row.ci95_low, row.ci95_high, color=COLORS[algorithm])
    ax.set(xlabel=x.replace("_", " "), ylabel=metric.replace("_", " "))
    ax.grid(axis="y", alpha=.2)
    ax.legend(fontsize=7)


def make_figures(directory="results/summaries", output="results/figures", study="screening_stage2"):
    directory, output = Path(directory), Path(output)
    summary = pd.read_csv(directory / "summary.csv")
    summary = summary[(summary.study == study) & summary.ablation_factor.eq("baseline") & (summary.n > 0)]
    if summary.empty:
        raise ValueError(f"No audited observations for study {study}")
    paths = []
    x = "time_limit" if study == "realtime" else "DoD_target"
    for name, metric in [("service_vs_dod", "service_ratio"), ("unserved_vs_dod", "customers_unserved"),
                         ("complete_vs_dod", "complete_service"),
                         ("vehicles_vs_dod", "vehicles_activated"), ("distance_vs_dod", "distance_complete"),
                         ("mean_latency", "mean_planning_time"), ("median_latency", "median_planning_time"),
                         ("p95_latency", "p95_planning_time"), ("max_latency", "maximum_planning_time"),
                         ("deadline_overrun", "deadline_overrun_rate")]:
        data = summary[summary.metric == metric]
        if data.empty:
            continue
        fig, ax = plt.subplots(figsize=(7, 4))
        _panel(ax, data, x, metric)
        condition = ("; complete-service subset, not a ranking" if metric == "distance_complete"
                     else "; descriptive, compare service first" if metric == "vehicles_activated"
                     else "; descriptive scenario-level intervals")
        ax.set_title(study + condition, fontsize=10)
        paths.append(save_figure(fig, data, output / "main" / name))
    pairs = pd.read_csv(directory / "paired_comparisons.csv")
    if "study" in pairs:
        pairs = pairs[(pairs.study == study) & (pairs.n > 0)]
    else:
        pairs = pairs.iloc[:0]
    for baseline, group in pairs.groupby("second") if "second" in pairs else []:
        for metric, data in group.groupby("metric"):
            if len(data) != 1:
                raise ValueError("Multiple paired configurations; select a single configuration")
            row = data.iloc[0]
            fig, ax = plt.subplots(figsize=(7, 3))
            ax.axvline(0, color="grey", linewidth=.7)
            ax.scatter([row["mean"]], [0], color=COLORS["COORDINATED_MPC_MCTS"])
            if pd.notna(row.ci95_low) and pd.notna(row.ci95_high):
                ax.hlines(0, row.ci95_low, row.ci95_high)
            ax.set(yticks=[], xlabel=f"{metric}: coordinated minus {LABELS.get(baseline, baseline)}",
                   title=f"{row['condition']}; n={row['n']}")
            paths.append(save_figure(fig, data, output / "paired" / f"{baseline}_{metric}"))
    return paths

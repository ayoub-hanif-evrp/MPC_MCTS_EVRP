"""CSV-driven publication figures and one pre-specified qualitative trace."""

from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .audit import audited_records
from .experiments import load_config
from .instance import load_instance
from .storage import BENCHMARK, save_json, writable_path

ORDER = ["GREEDY", "MPC_MCTS_H1", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"]
LABELS = dict(zip(ORDER, ["Greedy", "MPC-MCTS H1", "Independent MPC-MCTS", "Coordinated MPC-MCTS"]))
COLORS = dict(zip(ORDER, ["#727272", "#cc7933", "#24865b", "#316caa"]))
MARKERS = dict(zip(ORDER, ["s", "^", "D", "o"]))


def save_figure(fig, data, stem):
    stem = Path(stem)
    data.to_csv(writable_path(stem.with_name(stem.name + "_data.csv")), index=False)
    fig.tight_layout()
    fig.savefig(writable_path(stem.with_name(stem.name + ".png")), dpi=300, bbox_inches="tight")
    plt.close(fig)
    return str(stem.with_name(stem.name + ".png"))


def _panel(ax, data, x, metric, title):
    subset = data[data.metric == metric] if "metric" in data else data.iloc[:0]
    subset = subset[subset["n"] > 0] if "n" in subset else subset
    if subset.empty:
        ax.text(0.5, 0.5, "No eligible observations", ha="center", va="center", transform=ax.transAxes)
    else:
        groups = []
        profiles = sorted(subset.execution_profile.unique()) if "execution_profile" in subset else [None]
        for algorithm in ORDER:
            for profile in profiles:
                group = subset[subset.algorithm == algorithm]
                if profile is not None:
                    group = group[group.execution_profile == profile]
                groups.append((algorithm, profile, group.sort_values(x)))
        for algorithm, profile, group in groups:
            if group.empty:
                continue
            if group.duplicated(x).any():
                raise ValueError("Multiple configurations at one figure point; select a single study/configuration")
            values = group[x].astype(str) if group[x].dtype == object else group[x]
            label = LABELS[algorithm] + (f" ({profile})" if len(profiles) > 1 else "")
            ax.plot(values, group["mean"], marker=MARKERS[algorithm], color=COLORS[algorithm], label=label,
                    linestyle="--" if profile == "concurrent" else "-")
            for position, (_, row) in zip(values, group.iterrows()):
                if pd.notna(row.ci95_low) and pd.notna(row.ci95_high):
                    low, high = row.ci95_low, row.ci95_high
                    if metric in {"service_ratio", "complete_service"}:
                        low, high = max(0, low), min(1, high)
                    ax.errorbar(position, row["mean"], yerr=[[row["mean"] - low], [high - row["mean"]]],
                                color=COLORS[algorithm], capsize=3)
        ax.legend(fontsize=7)
    ax.set(xlabel=x.replace("_", " "), ylabel=metric.replace("_", " "), title=title)
    if metric in {"service_ratio", "complete_service"}:
        ax.set_ylim(0, 1.05)
    else:
        ax.set_ylim(bottom=0)
    ax.grid(axis="y", alpha=0.2)


def make_figures(directory="results/summaries", output="results/figures", study="pilot"):
    directory, output = Path(directory), Path(output)
    summary = pd.read_csv(directory / "summary.csv")
    summary = summary[summary.study == study]
    summary = summary[summary.ablation_factor == "baseline"]
    paths = []
    specifications = [
        ("service_vs_dod", "DoD_target", ["service_ratio", "complete_service"],
         ["Service ratio", "Full-service probability"]),
        ("vehicles_vs_dod", "DoD_target", ["vehicles_activated"], ["Vehicle use: interpret alongside service"]),
        ("distance_vs_dod", "DoD_target", ["distance_complete"], ["Distance: complete-service runs only"]),
    ]
    for name, x, metrics, titles in specifications:
        data = summary[summary.metric.isin(metrics)].copy()
        fig, axes = plt.subplots(1, len(metrics), figsize=(6 * len(metrics), 4), squeeze=False)
        for ax, metric, title in zip(axes[0], metrics, titles):
            _panel(ax, data, x, metric, title)
        fig.suptitle(f"{study.upper()} study; descriptive scenario-level intervals")
        paths.append(save_figure(fig, data, output / "main" / name))
    pairs = pd.read_csv(directory / "paired_comparisons.csv")
    if "study" in pairs:
        pairs = pairs[(pairs.study == study) & (pairs.second == "INDEPENDENT_MPC_MCTS")]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    for ax, metric in zip(axes, ["customers_unserved", "vehicles_activated", "total_distance"]):
        values = pairs[pairs.metric == metric]
        values = values[values.n > 0]
        ax.axhline(0, color="grey", linewidth=0.7)
        if len(values):
            row = values.iloc[0]
            ax.scatter([0], [row["mean"]], color=COLORS["COORDINATED_MPC_MCTS"])
            if pd.notna(row.get("ci95_low")):
                ax.vlines(0, row.ci95_low, row.ci95_high)
        else:
            ax.text(.5, .5, "No eligible pairs", ha="center", transform=ax.transAxes)
        ax.set(xticks=[], title=metric.replace("_", " "), ylabel="Coordinated minus independent")
    fig.suptitle(f"{study.upper()}: vehicles require equal service; distance also equal vehicles")
    paths.append(save_figure(fig, pairs, output / "main" / "coordinated_vs_independent"))
    for factor, name, metrics in [
        ("prediction_horizon", "horizon", ["service_ratio", "distance_complete", "total_planning_time"]),
        ("iterations", "budget", ["service_ratio", "distance_complete", "total_planning_time"]),
        ("top_l", "top_l", ["service_ratio", "distance_complete", "total_planning_time"]),
        ("charging_mode", "charging", ["service_ratio", "distance_complete", "total_charging_time", "total_charging_visits"]),
    ]:
        data = pd.read_csv(directory / f"ablation_{factor}.csv")
        # The baseline row and its identical factor value must not be counted twice.
        data = data[data.ablation_factor != "baseline"] if "ablation_factor" in data else data
        data = data[data.metric.isin(metrics)]
        fig, axes = plt.subplots(1, len(metrics), figsize=(5 * len(metrics), 4), squeeze=False)
        for ax, metric in zip(axes[0], metrics):
            title = "Complete-service runs only" if metric == "distance_complete" else metric.replace("_", " ")
            _panel(ax, data, factor, metric, title)
        fig.suptitle(f"{name.title()} ablation" + (": not run" if data.empty else ""))
        paths.append(save_figure(fig, data, output / "ablations" / name))
    computation = pd.read_csv(directory / "computation.csv")
    computation = computation[(computation.study == study) & computation.ablation_factor.eq("baseline")]
    # DoD is deliberately kept separate rather than silently pooling scenarios/configurations.
    for dod, group in computation.groupby("DoD_target"):
        data = group[group.metric.isin(["mean_planning_time", "p95_planning_time"])]
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        for ax, metric in zip(axes, ["mean_planning_time", "p95_planning_time"]):
            _panel(ax, data, "number_of_customers", metric, metric.replace("_", " ") + " (seconds)")
        fig.suptitle(f"{study.upper()}: DoD={dod:g}; p95 is mean within-run p95")
        paths.append(save_figure(fig, data, output / "diagnostics" / f"latency_dod_{dod:g}"))
    return paths


def make_realtime_figures(directory="results/summaries", output="results/figures/realtime"):
    data = pd.read_csv(Path(directory) / "computation.csv")
    data = data[(data.study == "realtime") & (data.ablation_factor == "baseline")]
    paths = []
    metrics = ["service_ratio", "distance_complete", "mean_planning_time", "p95_planning_time"]
    for size, group in data.groupby("number_of_customers"):
        subset = group[group.metric.isin(metrics)]
        fig, axes = plt.subplots(1, len(metrics), figsize=(20, 4))
        for ax, metric in zip(axes, metrics):
            _panel(ax, subset, "time_limit", metric,
                   "Complete-service runs only" if metric == "distance_complete" else metric.replace("_", " "))
        fig.suptitle(f"Realtime study: {size} customers; configured wall-clock budget in seconds")
        paths.append(save_figure(fig, subset, Path(output) / f"budget_size_{size}"))
    return paths


def representative_figures(raw="results/raw/pilot", output="results/figures/representative",
                           config_path="configs/representative.yaml"):
    choice = load_config(config_path)
    runs, audits = audited_records(raw)
    selected = [r for r, a in zip(runs, audits) if a["structural_valid"] and r["status"] == "completed"
                and all(r["metadata"].get(k) == v for k, v in choice["metadata"].items())
                and all(r["effective_config"]["mpc"].get(k) == v for k, v in choice.get("mpc", {}).items())]
    if len(selected) != 1:
        raise ValueError(f"Pre-specified representative must identify exactly one audited run, found {len(selected)}")
    run = selected[0]
    output = Path(output)
    save_json("results/traces/representative/run.json", run)
    instance = load_instance(BENCHMARK / (run["metadata"]["instance"] + ".txt"))
    releases = dict(run["scenario"]["customer_release_times"])
    paths, geometry = [], []
    for node in (instance.infrastructure.depot,) + instance.infrastructure.stations + instance.customers:
        geometry.append(dict(kind="node", id=node.id, node_kind=node.kind, x=node.x, y=node.y,
                             dynamic=releases.get(node.id, 0) > 0, vehicle=None, x_end=None, y_end=None))
    for s in run["steps"]:
        if s["distance"] > 0:
            a, b = s["before"]["location"], s["after"]["location"]
            geometry.append(dict(kind="arc", id="", node_kind="", x=a["x"], y=a["y"], dynamic=False,
                                 vehicle=s["before"]["id"], x_end=b["x"], y_end=b["y"]))
    geometry = pd.DataFrame(geometry)
    fig, ax = plt.subplots(figsize=(8, 6))
    for kind, dynamic, marker, label in [("d", False, "s", "Depot"), ("f", False, "^", "Station"),
                                        ("c", False, "o", "Initially known"), ("c", True, "D", "Dynamic")]:
        nodes = geometry[(geometry.kind == "node") & (geometry.node_kind == kind) & (geometry.dynamic == dynamic)]
        ax.scatter(nodes.x, nodes.y, marker=marker, label=label, s=40)
        for row in nodes.itertuples():
            offset = (-22, -13) if row.node_kind == "d" else (4, 4)
            ax.annotate(row.id, (row.x, row.y), xytext=offset, textcoords="offset points", fontsize=7)
    ax.margins(.10)
    for vehicle, arcs in geometry[geometry.kind == "arc"].groupby("vehicle"):
        for index, row in enumerate(arcs.itertuples()):
            ax.plot([row.x, row.x_end], [row.y, row.y_end], color=plt.get_cmap("tab10")(int(vehicle)),
                    alpha=.65, label=f"EV {int(vehicle)}" if index == 0 else None)
    ax.set(xlabel="x", ylabel="y", aspect="equal", title=f"Pre-specified {instance.name}, DoD={run['metadata']['DoD_target']}")
    ax.legend(fontsize=8, loc="best")
    paths.append(save_figure(fig, geometry, output / "routes"))
    rows = []
    for customer, release in releases.items():
        step = next((s for s in run["steps"] if s["served"] == customer), None)
        rows.append(dict(customer=customer, release=release,
                         dispatch=step["before"]["time"] if step else np.nan,
                         service=step["service_start"] if step else np.nan,
                         vehicle=step["before"]["id"] if step else None))
    timeline = pd.DataFrame(rows).sort_values(["release", "customer"])
    fig, ax = plt.subplots(figsize=(9, 4))
    y = range(len(timeline))
    ax.scatter(timeline.release, y, label="Release", marker="|")
    ax.scatter(timeline.dispatch, y, label="Assignment", marker="x")
    ax.scatter(timeline.service, y, label="Service start", marker="o")
    ax.set(yticks=list(y), yticklabels=[f"{r.customer} (EV {int(r.vehicle) if pd.notna(r.vehicle) else 'unserved'})" for r in timeline.itertuples()],
           xlabel="Simulation time", title="Customer disclosure, assignment and service")
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1, 1))
    paths.append(save_figure(fig, timeline, output / "customer_timeline"))
    rows = []
    for i, s in enumerate(run["steps"]):
        b, a = s["before"], s["after"]
        arrival_soc = b["battery"] - s["distance"] * instance.infrastructure.parameters.consumption
        for phase, time, soc in [("departure", b["time"], b["battery"]), ("arrival", s["arrival"], arrival_soc),
                                 ("start", s["service_start"], arrival_soc), ("finish", a["time"], a["battery"])]:
            rows.append(dict(vehicle=b["id"], step=i, phase=phase, time=time, soc=soc, action=s["action"]["kind"]))
    soc = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(9, 4))
    for vehicle, group in soc.groupby("vehicle"):
        group = group.sort_values("time", kind="stable")
        ax.plot(group.time, group.soc, label=f"EV {vehicle}")
        charges = group[(group.action == "charge") & (group.phase == "finish")]
        ax.scatter(charges.time, charges.soc, marker="^", s=65, label=f"EV {vehicle} recharge")
    ax.set(xlabel="Simulation time", ylabel="SOC (energy units)", ylim=(0, instance.infrastructure.parameters.battery * 1.05), title="SOC with completed charging events")
    ax.legend(fontsize=8)
    paths.append(save_figure(fig, soc, output / "soc"))
    rows = [dict(time=d["time"], vehicle=int(v), action=p["actions"][0]["kind"],
                 destination=p["actions"][0]["destination"], event="decision")
            for d in run["decisions"] for v, p in d["plans"].items()]
    rows += [dict(time=t, vehicle=-1, action="release", destination=c, event="release") for c, t in releases.items()]
    decisions = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(11, 4))
    for action, group in decisions.groupby("action"):
        ax.scatter(group.time, group.vehicle, label=action, s=26)
    vehicles = sorted(decisions.vehicle.unique())
    ax.set(xlabel="Simulation time", ylabel="Vehicle", yticks=vehicles,
           yticklabels=["Releases" if v == -1 else f"EV {v}" for v in vehicles],
           title="MPC first actions and request releases")
    ax.legend(fontsize=8, ncol=5)
    paths.append(save_figure(fig, decisions, output / "decisions"))
    def competing(decision):
        tails = [(v, set(p["predicted_customer_sequence"])) for v, choices in decision["candidates"].items() for p in choices]
        return any(v != w and a & b for i, (v, a) in enumerate(tails) for w, b in tails[i + 1:])
    epoch = next((d for d in run["decisions"] if competing(d)), run["decisions"][0])
    rows = []
    for vehicle, choices in epoch["candidates"].items():
        for p in choices:
            rows.append(dict(epoch=epoch["epoch"], time=epoch["time"], vehicle=vehicle,
                             first_action=str(p["actions"][0]), predicted_tail=" -> ".join(p["predicted_customer_sequence"]),
                             service_coverage=p["predicted_service_count"], distance=p["total_predicted_distance"],
                             new_activation=p["new_activation"], selected=p == epoch["plans"][vehicle]))
    table = pd.DataFrame(rows)
    table.to_csv(writable_path(output / "coordination_example.csv"), index=False)
    writable_path(output / "coordination_example.tex").write_text(table.to_latex(index=False, escape=True, float_format="%.2f"), encoding="utf-8")
    return paths

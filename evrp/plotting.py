"""Standalone matplotlib research figures, never a dashboard."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .analysis import load_runs, run_frame
from .instance import load_instance
from .storage import BENCHMARK, writable_path


def _save(fig, path):
    fig.tight_layout()
    fig.savefig(writable_path(path), dpi=180)
    plt.close(fig)


def make_figures(directory="results/runs", output="results/figures") -> list[str]:
    runs = load_runs(directory)
    completed = [r for r in runs if r["status"] == "completed"]
    if not completed:
        raise ValueError("No completed runs to plot")
    paths = []
    for index, run in enumerate(completed):
        instance = load_instance(BENCHMARK / (run["metadata"]["instance"] + ".txt"))
        stem = f"{instance.name}_{run['metadata']['algorithm']}_{index}"
        for draw_routes in (False, True):
            fig, ax = plt.subplots(figsize=(7, 6))
            ax.scatter([c.x for c in instance.customers], [c.y for c in instance.customers], s=22, label="Customers")
            ax.scatter([s.x for s in instance.infrastructure.stations], [s.y for s in instance.infrastructure.stations], marker="^", color="#278568", label="Stations")
            depot = instance.infrastructure.depot
            ax.scatter([depot.x], [depot.y], marker="s", color="black", s=65, label="Depot")
            if draw_routes:
                for step in run["steps"]:
                    if step["action"]["kind"] == "wait":
                        continue
                    a, b = step["before"]["location"], step["after"]["location"]
                    ax.plot([a["x"], b["x"]], [a["y"], b["y"]], color=plt.get_cmap("tab10")(step["before"]["id"] % 10), linewidth=1, alpha=0.8)
            ax.set(xlabel="x", ylabel="y", title=instance.name, aspect="equal")
            ax.legend()
            path = Path(output) / f"{stem}_{'routes' if draw_routes else 'geometry'}.png"
            _save(fig, path)
            paths.append(str(path))
        vehicles = sorted({s["before"]["id"] for s in run["steps"] if s["after"]["departed"]})
        if vehicles:
            chosen = vehicles[0]
            fig, ax = plt.subplots(figsize=(8, 3))
            for step in run["steps"]:
                if step["before"]["id"] != chosen:
                    continue
                before, after = step["before"], step["after"]
                arrival_battery = before["battery"] - step["distance"] * instance.infrastructure.parameters.consumption
                ax.plot([before["time"], step["arrival"], step["service_start"], after["time"]],
                        [before["battery"], arrival_battery, arrival_battery, after["battery"]], color="#286da8")
            ax.set(xlabel="Simulation time", ylabel="SOC (energy units)", title=f"{instance.name}, EV {chosen}", ylim=(0, instance.infrastructure.parameters.battery * 1.05))
            path = Path(output) / f"{stem}_soc.png"
            _save(fig, path)
            paths.append(str(path))
        if run.get("scenario_path"):
            import json
            scenario = json.loads(Path(run["scenario_path"]).read_text(encoding="utf-8"))
            releases = sorted(scenario["customer_release_times"], key=lambda pair: pair[1])
            fig, ax = plt.subplots(figsize=(8, 3))
            ax.scatter([t for _, t in releases], range(len(releases)), s=12)
            ax.set(xlabel="Release time", ylabel="Customer index (sorted)", title=instance.name)
            path = Path(output) / f"{stem}_releases.png"
            _save(fig, path)
            paths.append(str(path))
    frame = run_frame(completed)
    figures = [("DoD_realized", "total_distance", "distance_dynamicity"),
               ("DoD_realized", "service_ratio", "service_dynamicity"),
               ("number_of_customers", "mean_planning_time", "latency_size"),
               ("prediction_horizon", "total_distance", "horizon_ablation"),
               ("iterations", "total_distance", "budget_ablation"),
               ("top_l", "total_distance", "top_l_ablation"),
               ("algorithm", "service_ratio", "coordination"),
               ("charging_mode", "total_distance", "charging_ablation")]
    for x, y, name in figures:
        if x not in frame or y not in frame:
            continue
        fig, ax = plt.subplots(figsize=(8, 4))
        for algorithm, group in frame.groupby("algorithm"):
            ax.scatter(group[x], group[y], label=algorithm, alpha=0.8, s=24)
        ax.set(xlabel=x.replace("_", " "), ylabel=y.replace("_", " "))
        ax.legend(fontsize=7)
        if frame[x].dtype == object:
            ax.tick_params(axis="x", labelrotation=20)
        path = Path(output) / f"{name}.png"
        _save(fig, path)
        paths.append(str(path))
    return paths

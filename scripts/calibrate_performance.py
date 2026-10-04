"""Run only the declared 24 calibration cases, not the paper campaign."""

import os
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
from pathlib import Path
from time import perf_counter

from evrp.audit import audit_record
from evrp.experiments import prepare, run_single, source_fingerprint
from evrp.paper import CALIBRATION, canonical_config, select_budget
from evrp.runtime import peak_memory_mib, worker_capacity
from evrp.storage import load_json, save_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("results/performance/calibration.json"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = source_fingerprint()
    previous = load_json(args.output / "progress.json") if (args.output / "progress.json").exists() else {}
    # Preserve first cold-reference setup measurements when rerunning online timing.
    prior_preparations = {r["instance"]: r for r in previous.get("preparations", [])}
    rows, preparations = [], []
    for instance in CALIBRATION:
        cfg = canonical_config(dict(algorithm="COORDINATED_MPC_MCTS", mcts_iterations=32))
        start = perf_counter()
        prepare(instance, cfg)
        seconds = perf_counter()-start
        preparations.append(dict(instance=instance, seconds=max(seconds, prior_preparations.get(instance, {}).get("seconds", 0))))
        for budget in (8, 16, 32, 64):
            if source_fingerprint() != source:
                raise RuntimeError("Source changed during calibration")
            config = canonical_config({**cfg, "mcts_iterations": budget})
            config["execution_profile"] = "isolated"
            start = perf_counter()
            path = run_single(instance, config, args.output / "raw", resume=False)
            wall = perf_counter()-start
            result = load_json(path)
            errors = audit_record(result)
            row = dict(instance=instance, iterations=budget, wall_seconds=wall,
                       path=str(path), status=result["status"], audit_errors=errors,
                       peak_memory_mib=peak_memory_mib(), **result["metrics"])
            rows.append(row)
            save_json(args.output / "progress.json", dict(source_sha256=source, rows=rows,
                                                         preparations=preparations))
            print({k: row.get(k) for k in ("instance", "iterations", "wall_seconds", "customers_served",
                                           "vehicles_activated", "status", "audit_errors")}, flush=True)
            if errors or result["status"] != "completed":
                raise RuntimeError(f"Calibration failed: {row}")
    selection = select_budget(rows)
    report = dict(source_sha256=source, rows=rows, preparations=preparations,
                  selection=selection, timing_context="isolated; BLAS threads=1; no cProfile",
                  workers=worker_capacity(max(r["peak_memory_mib"] for r in rows), requested=4))
    save_json(args.report, report)
    import pandas as pd
    from evrp.plotting import save_figure
    import matplotlib.pyplot as plt
    frame = pd.DataFrame(rows)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    frame.drop(columns="audit_errors").to_csv(args.report.parent / "calibration.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for instance, group in frame.groupby("instance"):
        axes[0].plot(group.iterations, group.customers_served, marker="o", label=instance)
        axes[1].plot(group.iterations, group.wall_seconds, marker="o", label=instance)
    axes[0].set(ylabel="Customers served", xlabel="Iterations per MCTS call")
    axes[1].set(ylabel="Isolated run time (seconds)", xlabel="Iterations per MCTS call")
    axes[1].legend(fontsize=8)
    fig.tight_layout()
    save_figure(fig, frame.drop(columns="audit_errors"), args.report.parent / "calibration")
    frame[["instance", "iterations", "customers_served", "vehicles_activated", "total_distance",
           "total_planning_time", "median_planning_time", "p95_planning_time", "nodes_expanded"]].to_latex(
        args.report.parent / "calibration.tex", index=False, float_format="%.3f", escape=True)
    print(selection, flush=True)


if __name__ == "__main__":
    main()

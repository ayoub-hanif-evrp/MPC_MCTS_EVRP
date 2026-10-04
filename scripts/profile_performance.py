"""Isolated, audited full-run profiles at explicitly requested small budgets."""

import os
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
import cProfile
from dataclasses import asdict
import io
from pathlib import Path
import pstats
from time import perf_counter
from unittest.mock import patch

from evrp import performance
from evrp.experiments import prepare, simulation_config, audit_result, source_fingerprint
from evrp.simulator import EventDrivenSimulator
import evrp.simulator as simulator
from evrp.storage import save_json


def profile_run(budget, output, label):
    config = dict(algorithm="COORDINATED_MPC_MCTS", dynamicity=.5, scenario_seed=0,
                  experiment_seed=0, prediction_horizon=5, top_L=3, mcts_iterations=budget,
                  charging_mode="partial", trace_level="full")
    instance, _, scenario, _ = prepare("c101_21", config)
    profiler = cProfile.Profile()
    measured = performance.Measurements()
    original_coordinate = simulator.coordinate
    def coordinate(*args, **kwargs):
        start = performance.stamp()
        result = original_coordinate(*args, **kwargs)
        performance.elapsed("coordinator_milps", start)
        performance.count("coordinator_epochs")
        return result
    start = perf_counter()
    with measured, patch.object(simulator, "coordinate", coordinate):
        profiler.enable()
        result = EventDrivenSimulator(instance, scenario, simulation_config(config)).run()
        profiler.disable()
    wall = perf_counter() - start
    start = perf_counter()
    audit = audit_result(result, instance, scenario)
    audit_seconds = perf_counter() - start
    start = perf_counter()
    save_json(output / f"{label}_{budget}_trace.json.gz", asdict(result))
    serialization = perf_counter() - start
    stats = pstats.Stats(profiler)
    names = {"actions", "customer_pool", "charge_actions", "customer_rank", "transition", "escape", "terminal_cost", "proposal", "proposal_from_state",
             "coordinate", "milp", "solve", "rollout_action", "predict", "distance"}
    functions = []
    for (file, line, name), (primitive, calls, own, cumulative, _) in stats.stats.items():
        if name in names:
            functions.append(dict(file=Path(file).name, line=line, name=name, calls=calls,
                                  own_seconds=own, cumulative_seconds=cumulative))
    report = dict(label=label, iterations=budget, wall_seconds=wall,
                  audit_seconds=audit_seconds, serialization_seconds=serialization,
                  source_sha256=source_fingerprint(), scenario_hash=scenario.identifier,
                  metrics=result.metrics, audit=audit, measurements=measured.report(),
                  functions=functions,
                  simulations_per_agent=[{k: s[k] for k in ("epoch", "vehicle_id", "iterations", "elapsed")}
                                         for s in result.searches])
    save_json(output / f"{label}_{budget}.json", report)
    profiler.dump_stats(str(output / f"{label}_{budget}.prof"))
    print(dict(label=label, budget=budget, seconds=round(wall, 3),
               served=result.metrics["customers_served"], measurements=measured.report()), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", default="before")
    parser.add_argument("--budgets", nargs="+", type=int, default=[8, 16, 32])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for budget in args.budgets:
        profile_run(budget, args.output, args.label)


if __name__ == "__main__":
    main()

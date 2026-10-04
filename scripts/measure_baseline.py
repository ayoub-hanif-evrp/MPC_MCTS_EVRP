"""Unprofiled control and seeded physical golden traces before optimization."""

import os
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from evrp.experiments import prepare, simulation_config, audit_result, source_fingerprint
from evrp.simulator import EventDrivenSimulator
from evrp.storage import save_json
import evrp.simulator as simulator


def main():
    output = Path(os.environ["TEMP"]) / "evrp-performance"
    config = dict(algorithm="COORDINATED_MPC_MCTS", dynamicity=.5, scenario_seed=0,
                  experiment_seed=0, prediction_horizon=5, top_L=3, mcts_iterations=32,
                  charging_mode="partial")
    instance, _, scenario, _ = prepare("c101_21", config)
    coordination, unused = [], {}
    original_coordinate, original_plan = simulator.coordinate, simulator._plan_job

    def coordinate(*args, **kwargs):
        start = perf_counter()
        result = original_coordinate(*args, **kwargs)
        coordination.append(perf_counter() - start)
        return result

    def plan(agent, state, observation, seed, algorithm):
        start = perf_counter()
        result = original_plan(agent, state, observation, seed, algorithm)
        if not state.departed and state.location.kind == "d":
            key = (observation.time, state.location, state.time, state.battery, state.load,
                   observation, agent.controller.config)
            unused.setdefault(key, []).append(perf_counter() - start)
        return result

    start = perf_counter()
    with patch.object(simulator, "coordinate", coordinate), patch.object(simulator, "_plan_job", plan):
        result = EventDrivenSimulator(instance, scenario, simulation_config(config)).run()
    report = dict(wall_seconds=perf_counter()-start, coordinator_seconds=sum(coordination),
                  coordinator_calls=len(coordination), metrics=result.metrics,
                  repeated_unused_search_seconds=sum(sum(v[1:]) for v in unused.values()),
                  repeated_unused_searches=sum(len(v)-1 for v in unused.values()),
                  audit=audit_result(result, instance, scenario), source_sha256=source_fingerprint())
    save_json(output / "before_unprofiled_32.json", report)
    print(report, flush=True)
    for name in ("c101C5", "r104C5", "rc105C5"):
        cfg = {**config, "mcts_iterations": 8}
        instance, _, scenario, _ = prepare(name, cfg)
        result = EventDrivenSimulator(instance, scenario, simulation_config(cfg)).run()
        save_json(output / f"golden_{name}.json.gz", dict(config=cfg, result=asdict(result)))
        print(name, result.metrics["customers_served"], flush=True)


if __name__ == "__main__":
    main()

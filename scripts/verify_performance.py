"""Physical golden-trace equality and optional symmetry behavior comparison."""

import os
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

from dataclasses import asdict
from pathlib import Path

from evrp.experiments import prepare, simulation_config, audit_result
from evrp.simulator import EventDrivenSimulator
from evrp.storage import load_json, save_json, canonical


def main():
    root = Path(__file__).resolve().parents[1] / "tests/fixtures/performance"
    rows = []
    for name in ("c101C5", "r104C5", "rc105C5"):
        golden = load_json(root / f"golden_{name}.json.gz")
        config = {**golden["config"], "action_space_reduction": False}
        instance, _, scenario, _ = prepare(name, config)
        exact = EventDrivenSimulator(instance, scenario, simulation_config(config)).run()
        original = golden["result"]
        assert canonical(asdict(exact)["steps"]) == canonical(original["steps"])
        assert canonical(asdict(exact)["events"]) == canonical(original["events"])
        assert all(audit_result(exact, instance, scenario).values())
        results = []
        for reuse in (False, True):
            result = EventDrivenSimulator(instance, scenario, simulation_config(
                {**config, "action_space_reduction": True, "symmetry_reuse": reuse})).run()
            assert all(audit_result(result, instance, scenario).values())
            results.append(result)
        rows.append(dict(instance=name, exact_optimization_physical_equality=True,
                         symmetry_same_steps=results[0].steps == results[1].steps,
                         ordinary={k: results[0].metrics[k] for k in ("customers_served", "vehicles_activated", "total_distance")},
                         symmetry={k: results[1].metrics[k] for k in ("customers_served", "vehicles_activated", "total_distance")},
                         reused_replans=results[1].metrics["symmetry_reused_replans"]))
    save_json("results/performance/exact_and_symmetry_checks.json", rows)
    print(rows)


if __name__ == "__main__":
    main()

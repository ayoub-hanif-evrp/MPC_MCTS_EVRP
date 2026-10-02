from dataclasses import replace
import json

import pytest

from evrp.analysis import aggregate, describe
from evrp.experiments import audit_result, load_config, run_single, static_reference_result
from evrp.instance import load_instance
from evrp.reference import ReferenceConfig, ReferenceSchedule, solve_reference
from evrp.scenario import generate
from evrp.storage import BENCHMARK, save_json


def test_reference_save_load(tmp_path):
    instance = load_instance(BENCHMARK / "r104C5.txt")
    reference = solve_reference(instance, ReferenceConfig(multistarts=1))
    path = tmp_path / "reference.json"
    reference.save(path)
    assert ReferenceSchedule.load(path, instance) == reference


def test_static_reference_replays_in_dynamic_scenario():
    instance = load_instance(BENCHMARK / "rc105C5.txt")
    reference = solve_reference(instance, ReferenceConfig(multistarts=1))
    scenario = generate(instance, reference, 12, 0.5)
    result = static_reference_result(instance, reference, scenario, {})
    assert all(audit_result(result, instance, scenario).values())
    step = next(s for s in result.steps if s.served)
    result.steps[result.steps.index(step)] = replace(step, distance=999)
    with pytest.raises(AssertionError, match="replay"):
        audit_result(result, instance, scenario)


def test_statistics_and_singleton_uncertainty():
    assert describe([7])["ci95_low"] is None
    summary = describe([1, 2, 3])
    assert summary["mean"] == summary["median"] == 2
    assert summary["standard_deviation"] == 1
    assert summary["ci95_low"] < 1 < summary["ci95_high"]


def test_failure_kept_in_aggregation(tmp_path):
    inputs = tmp_path / "runs"
    save_json(inputs / "a.json", {"status": "failed", "metadata": {"algorithm": "GREEDY", "DoD_target": 0.5}, "metrics": {"feasible": False}})
    save_json(inputs / "b.json", {"status": "completed", "metadata": {"algorithm": "GREEDY", "DoD_target": 0.5}, "metrics": {"feasible": False, "service_ratio": 0.5, "total_distance": 12}})
    note = aggregate(inputs, tmp_path / "aggregate")
    assert note["runs"] == 2 and note["failed_runs"] == 1


def test_run_failure_is_written_and_original_data_untouched(tmp_path):
    config = {**load_config("configs/debug.yaml"), "algorithm": "unknown"}
    path = run_single("c101C5", config, tmp_path)
    result = json.loads(path.read_text())
    assert result["status"] == "failed"
    assert not result["metrics"]["feasible"]
    assert "Invalid simulation" in result["error"]

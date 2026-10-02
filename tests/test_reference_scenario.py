from dataclasses import replace

import pytest

from evrp.instance import load_instance
from evrp.reference import ReferenceConfig, ReferenceFailure, solve_reference, validate_reference
from evrp.scenario import DynamicScenario, generate
from evrp.storage import BENCHMARK, benchmark_hashes


@pytest.fixture(scope="module")
def reference():
    instance = load_instance(BENCHMARK / "c101C5.txt")
    return instance, solve_reference(instance, ReferenceConfig(multistarts=2))


@pytest.mark.parametrize("name", ["c101C5", "r104C5", "rc105C5", "c101C10", "c103C15"])
def test_reference_feasible(name):
    before = benchmark_hashes()
    instance = load_instance(BENCHMARK / f"{name}.txt")
    schedule = solve_reference(instance, ReferenceConfig(multistarts=1))
    validate_reference(instance, schedule)
    assert schedule.fleet_size > 0
    assert all(step.after.battery == instance.infrastructure.parameters.battery
               for route in schedule.routes for step in route.steps if step.action.kind == "charge")
    assert before == benchmark_hashes()


def test_reference_determinism(reference):
    instance, schedule = reference
    assert solve_reference(instance, schedule.config) == schedule


@pytest.mark.parametrize("mode", ["exact_count", "bernoulli"])
def test_scenario_deterministic_and_preserves_schedule(reference, mode, tmp_path):
    instance, schedule = reference
    scenario = generate(instance, schedule, 12, 0.5, mode)
    assert scenario == generate(instance, schedule, 12, 0.5, mode)
    for key, time in scenario.customer_release_times:
        assert time <= schedule.predecessor_departures[key]
    path = tmp_path / "scenario.json"
    scenario.save(path)
    assert DynamicScenario.load(path, instance) == scenario


def test_ineligible_customers_remain_static(reference):
    instance, schedule = reference
    scenario = generate(instance, schedule, 7, 1)
    releases = dict(scenario.customer_release_times)
    assert all(releases[key] == 0 for key, bound in scenario.release_upper_bounds if bound == 0)
    assert sum(time > 0 for time in releases.values()) == scenario.eligible_count


def test_scenario_mismatch(reference):
    instance, schedule = reference
    with pytest.raises(ValueError, match="mismatch"):
        generate(instance, schedule, 0).validate(replace(instance, sha256="wrong"))


def test_reference_failure_is_explicit(reference):
    instance, _ = reference
    broken = replace(instance, customers=tuple(replace(c, demand=10000) for c in instance.customers))
    with pytest.raises(ReferenceFailure, match="No feasible reference"):
        solve_reference(broken, ReferenceConfig(multistarts=1))

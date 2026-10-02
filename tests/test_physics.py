from dataclasses import replace

import pytest

from evrp.instance import Infrastructure, Location, Parameters, distance, load_instance
from evrp.model import (Action, InfeasibilityReason as Reason, Observation, VehicleState,
                        escape, escape_action, transition, try_transition)
from evrp.storage import BENCHMARK, benchmark_hashes, save_json


@pytest.fixture
def toy():
    depot = Location("D", "d", 0, 0, 0, 0, 200, 0)
    station = Location("S", "f", 6, 0, 0, 0, 200, 0)
    customer = Location("C", "c", 3, 4, 2, 10, 30, 7)
    infra = Infrastructure(depot, (station,), Parameters(20, 10, 2, 0.5, 2))
    state = VehicleState(0, depot, 0, 20, 10)
    return state, Observation(0, infra, (customer,))


@pytest.mark.parametrize("name,n,s", [("c101C5", 5, 3), ("c101C10", 10, 5),
                                     ("c103C15", 15, 5), ("c101_21", 100, 21),
                                     ("r104C5", 5, 3), ("rc105C5", 5, 4)])
def test_parser_counts(name, n, s):
    instance = load_instance(BENCHMARK / f"{name}.txt")
    assert len(instance.customers) == n
    assert len(instance.infrastructure.stations) == s
    assert instance.infrastructure.depot.kind == "d"
    assert all(c.kind == "c" for c in instance.customers)


def test_all_original_instances_parse_unchanged():
    before = benchmark_hashes()
    instances = [load_instance(p) for p in BENCHMARK.glob("*.txt") if p.name != "readme.txt"]
    assert len(instances) == 92
    assert benchmark_hashes() == before


def test_parameters():
    assert load_instance(BENCHMARK / "c101C5.txt").infrastructure.parameters == Parameters(77.75, 200, 1, 3.47, 1)


def test_no_fabricated_parameter(tmp_path):
    original = (BENCHMARK / "c101C5.txt").read_text()
    file = tmp_path / "missing.txt"
    file.write_text(original.replace("v average Velocity /1.0/", ""))
    with pytest.raises(ValueError, match="parameters"):
        load_instance(file)


def test_physical_service(toy):
    state, obs = toy
    step = transition(state, Action("serve", "C"), obs)
    assert distance(state.location, obs.customers[0]) == 5
    assert step.distance == 5
    assert step.travel_time == 2.5
    assert step.arrival == 2.5
    assert step.service_start == 10
    assert step.waiting_time == 7.5
    assert step.service_finish == 17
    assert step.energy_consumed == 10
    assert step.after.battery == 10
    assert step.after.load == 8
    assert state.battery == 20


@pytest.mark.parametrize("target,charged", [(20, 12), (12, 4)])
def test_linear_charging(toy, target, charged):
    state, obs = toy
    step = transition(state, Action("charge", "S", target), obs)
    assert step.after.battery == target
    assert step.energy_charged == charged
    assert step.charging_time == charged * 0.5
    assert step.after.time == 3 + charged * 0.5


@pytest.mark.parametrize("change,reason", [({"battery": 1}, Reason.BATTERY),
                                        ({"load": 1}, Reason.CAPACITY),
                                        ({"time": 40}, Reason.TIME_WINDOW)])
def test_constraints(toy, change, reason):
    state, obs = toy
    result = try_transition(replace(state, **change), Action("serve", "C"), obs)
    assert not result.feasible
    assert result.infeasibility_reason == reason


def test_reachable_customer_is_not_enough(toy):
    state, obs = toy
    result = try_transition(replace(state, battery=10), Action("serve", "C"), obs)
    assert not result.feasible
    assert result.infeasibility_reason == Reason.UNREACHABLE_SAFE_CONTINUATION


def test_no_zero_charge_or_depot_charge(toy):
    state, obs = toy
    assert not try_transition(state, Action("charge", "S", 8), obs).feasible
    assert not try_transition(state, Action("charge", "D", 20), obs).feasible


def test_escape_across_multiple_stations():
    depot = Location("D", "d", 0, 0, 0, 0, 100, 0)
    stations = tuple(Location(f"S{x}", "f", x, 0, 0, 0, 100, 0) for x in (8, 16))
    customer = Location("C", "c", 20, 0, 1, 0, 90, 0)
    infra = Infrastructure(depot, stations, Parameters(10, 10, 1, 0.5, 1))
    state = VehicleState(0, customer, 0, 4, 9, departed=True)
    route = escape(state, infra)
    assert route.distance == 20
    assert route.completion == 28
    assert [n.id for n in route.path] == ["S16", "S8", "D"]
    for _ in range(3):
        state = transition(state, escape_action(state, infra), Observation(0, infra, ())).after
    assert state.finished and state.time == 28


def test_write_protection():
    with pytest.raises(ValueError, match="read-only"):
        save_json(BENCHMARK / "do-not-write.json", {})

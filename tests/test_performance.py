from dataclasses import replace
from math import hypot
import pickle

import pytest

from evrp.instance import load_instance, distance
from evrp.model import Action, Observation, escape_action
from evrp.mpc import MPCConfig, MPCPlanningProblem
from evrp.mcts import MCTSOptimizer
from evrp.reference import initial_vehicle
from evrp.storage import BENCHMARK


def test_static_matrices_exact_and_immutable():
    instance = load_instance(BENCHMARK / "c101_21.txt")
    geometry = instance.geometry
    p = instance.infrastructure.parameters
    for i, a in enumerate(geometry.nodes):
        assert geometry.by_id[a.id] == a
        for j, b in enumerate(geometry.nodes):
            expected = hypot(a.x - b.x, a.y - b.y)
            assert geometry.distance[i][j] == distance(a, b) == expected
            assert geometry.travel_time[i][j] == expected / p.speed
            assert geometry.energy[i][j] == expected * p.consumption
    with pytest.raises(TypeError):
        geometry.by_id["secret"] = geometry.nodes[0]
    assert pickle.loads(pickle.dumps(instance)).geometry.distance == geometry.distance


def make_problem(**kwargs):
    instance = load_instance(BENCHMARK / "c101_21.txt")
    return MPCPlanningProblem(Observation(0, instance.infrastructure, instance.customers),
                              initial_vehicle(instance), MPCConfig(iterations=8, **kwargs))


def test_bounded_charging_and_customer_pool():
    problem = make_problem(station_candidate_limit=3, charge_target_limit=4)
    state = problem.initial
    for _ in range(5):
        actions = problem.actions(state)
        charging = [a for a in actions if a.kind == "charge"]
        assert len(charging) <= 3 * 4
        assert len({a.destination for a in charging}) <= 3
        assert len(problem.customer_pool(state)) <= 2 * problem.config.candidate_limit
        assert len({a for a in actions if a.kind == "serve"}) <= problem.config.candidate_limit
        for action in actions:
            problem.predict(state, action)
        serving = [a for a in actions if a.kind == "serve"]
        if not serving:
            break
        state, _ = problem.predict(state, serving[0])
        assert escape_action(state.vehicle, problem.observation.infrastructure) in problem.actions(state)


def test_transition_cache_reuses_complete_state(monkeypatch):
    import evrp.mpc as module
    problem = make_problem()
    original, calls = module.transition, []
    def transition(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(module, "transition", transition)
    action = problem.fallback(problem.initial)
    first = problem.predict(problem.initial, action)
    assert problem.predict(problem.initial, action) == first
    assert len(calls) == 1
    changed = replace(problem.initial, station_visits_since_service=frozenset({"unrelated"}))
    problem.predict(changed, action)
    assert len(calls) == 2


@pytest.mark.parametrize("seed", [0, 7, 19])
def test_exact_caching_and_incremental_proposal(seed):
    from tests.test_planning import problem
    p = problem(iterations=8, action_space_reduction=False)
    cached = MCTSOptimizer().solve(p, seed)
    uncached = MCTSOptimizer().solve(replace(p, config=replace(p.config, cache_transitions=False)), seed)
    assert cached.proposals == uncached.proposals
    for proposal in cached.proposals:
        replay = p.proposal(proposal.actions, proposal.visits)
        assert replace(replay, mcts_value_estimate=proposal.mcts_value_estimate) == proposal


def test_urgent_far_customer_not_dropped_by_nearest_preselection():
    from evrp.instance import Location
    p = make_problem(candidate_limit=1)
    depot = p.observation.infrastructure.depot
    urgent = Location("urgent", "c", depot.x + 8, depot.y, 1, 0, 9, 0)
    near = tuple(Location(f"near{i}", "c", depot.x + i/10, depot.y, 1, 0, 1000, 0) for i in range(1, 20))
    p = replace(p, observation=replace(p.observation, customers=near + (urgent,)))
    assert urgent in p.customer_pool(p.initial)


def test_no_hidden_customer_geometry_in_observation():
    p = make_problem()
    visible = p.observation.customers[:2]
    obs = replace(p.observation, customers=visible)
    assert set(obs.customer_by_id) == {c.id for c in visible}
    assert all(n.kind != "c" for n in obs.infrastructure.node_by_id.values())


def test_trace_levels_preserve_physical_decisions():
    from evrp.experiments import prepare, simulation_config, audit_result
    from evrp.simulator import EventDrivenSimulator
    config = dict(mcts_iterations=8, scenario_seed=0, dynamicity=.5, route_continuity=False, regret_repair=False)
    instance, _, scenario, _ = prepare("c101C5", config)
    results = []
    for level in ("full", "summary", "none"):
        result = EventDrivenSimulator(instance, scenario, simulation_config({**config, "trace_level": level})).run()
        assert all(audit_result(result, instance, scenario).values())
        results.append(result)
    assert results[0].steps == results[1].steps == results[2].steps
    assert results[0].events == results[1].events == results[2].events
    assert all("candidates" not in d for r in results[1:] for d in r.decisions)
    assert not results[2].searches
    metrics = lambda r: {k: v for k, v in r.metrics.items() if "planning_time" not in k}
    assert metrics(results[0]) == metrics(results[1]) == metrics(results[2])


def test_symmetry_key_excludes_active_or_physically_different_states():
    from evrp.simulator import unused_symmetry_key
    p = make_problem()
    a = p.current_state
    b = replace(a, id=1)
    assert unused_symmetry_key(a, p.observation, p.config) == unused_symmetry_key(b, p.observation, p.config)
    assert unused_symmetry_key(replace(b, departed=True), p.observation, p.config) is None
    assert unused_symmetry_key(replace(b, battery=b.battery-1), p.observation, p.config) != unused_symmetry_key(a, p.observation, p.config)
    assert unused_symmetry_key(a, replace(p.observation, customers=()), p.config) != unused_symmetry_key(a, p.observation, p.config)


def test_only_safe_return_station_survives_minimum_limits():
    from evrp.instance import Location, Infrastructure, Parameters
    from evrp.model import VehicleState
    depot = Location("D", "d", 0, 0, 0, 0, 100, 0)
    station = Location("S", "f", 5, 0, 0, 0, 100, 0)
    customer = Location("C", "c", 10, 0, 0, 0, 100, 0)
    infra = Infrastructure(depot, (station,), Parameters(10, 10, 1, .5, 1))
    vehicle = VehicleState(0, customer, 10, 5, 10, departed=True)
    problem = MPCPlanningProblem(Observation(10, infra, ()), vehicle,
                                 MPCConfig(station_candidate_limit=1, charge_target_limit=1))
    returning = escape_action(vehicle, infra)
    assert returning.kind == "charge"
    assert returning in problem.actions(problem.initial)
    following, _ = problem.predict(problem.initial, returning)
    assert problem.terminal_cost(following) < float("inf")


def test_reference_prefix_cache_preserves_exact_routes():
    from collections import OrderedDict
    from evrp.reference import evaluate_route, solve_reference
    instance = load_instance(BENCHMARK / "c101C5.txt")
    cache = OrderedDict()
    route = max(solve_reference(instance).routes, key=lambda r: len(r.customers)).customers
    sequences = [route[:length] for length in range(1, len(route)+1)] + [tuple(reversed(route))]
    assert evaluate_route(instance, route) is not None
    for sequence in sequences:
        assert evaluate_route(instance, sequence, prefix_cache=cache) == evaluate_route(instance, sequence)
    assert evaluate_route(instance, route, vehicle_id=7, prefix_cache=cache) == evaluate_route(instance, route, vehicle_id=7)
    assert len(cache) <= 512


def test_escape_geometry_cache_keeps_exact_time_and_battery():
    from evrp.model import escape, _escape_geometry
    p = make_problem()
    a = p.current_state
    first = escape(a, p.observation.infrastructure)
    second = escape(replace(a, time=a.time+3, id=99), p.observation.infrastructure)
    assert first.distance == second.distance and second.completion == first.completion+3
    assert _escape_geometry.cache_info().hits > 0


@pytest.mark.parametrize("name", ["c101C5", "r104C5", "rc105C5"])
def test_caching_preserves_final_method_physical_trace(name):
    from evrp.experiments import prepare, simulation_config, audit_result
    from evrp.simulator import EventDrivenSimulator
    config = dict(mcts_iterations=8, scenario_seed=0, dynamicity=.5, action_space_reduction=False)
    instance, _, scenario, _ = prepare(name, config)
    result = EventDrivenSimulator(instance, scenario, simulation_config(config)).run()
    uncached = EventDrivenSimulator(instance, scenario, simulation_config({**config, "cache_transitions": False})).run()
    assert result.steps == uncached.steps
    assert result.events == uncached.events
    assert all(audit_result(result, instance, scenario).values())

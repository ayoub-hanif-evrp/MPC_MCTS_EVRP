from dataclasses import replace

import pytest

from evrp.continuity import preserve_continuation, route_observation, service_tail
from evrp.coordinator import coordinate
from evrp.experiments import audit_result, prepare, simulation_config
from evrp.mcts import MCTSOptimizer
from evrp.model import Action
from evrp.mpc import MPCProposal, PlanningResult
from evrp.simulator import EventDrivenSimulator
from tests.test_planning import problem
from tests.test_simulator import synthetic


def test_exclusive_routes_do_not_double_promise_a_future_customer():
    a = MPCProposal((Action("serve", "A"), Action("serve", "C")), 2, vehicle_id=0)
    b = MPCProposal((Action("serve", "B"), Action("serve", "C")), 2, vehicle_id=1)
    idle = MPCProposal((Action("wait", wait_duration=1),), 0)
    result = coordinate({0: (a, idle), 1: (b, idle)}, available=frozenset({"A", "B", "C"}),
                        exclusive_routes=True)
    claims = [c for p in result.values() for c in p.unique_predicted_customer_set]
    assert len(claims) == len(set(claims))


def test_retained_suffix_survives_a_search_that_only_proposes_wait():
    p = problem(iterations=32, max_idle_wait=10, require_root_coverage=True)
    original = MCTSOptimizer().solve(p, 0).proposals[0]
    assert original.predicted_service_count > 1
    state, _ = p.predict(p.initial, original.first)
    obs = replace(p.observation, time=state.vehicle.time,
                  customers=tuple(c for c in p.observation.customers if c.id != original.first.destination))
    q = replace(p, observation=obs, current_state=state.vehicle)
    wait = q.proposal((Action("wait", wait_duration=1),))
    result = preserve_continuation(PlanningResult((wait,), wait), state.vehicle, obs, p.config,
                                   service_tail(original))
    assert result.candidates
    assert all(p.first.kind != "wait" for p in result.candidates)
    assert all(set(service_tail(original)) <= set(p.actions) for p in result.candidates)


def test_other_routes_cannot_see_reserved_work_but_owner_can():
    p = problem()
    key = p.observation.customers[0].id
    tails = {0: (Action("serve", key),)}
    assert key in route_observation(p.observation, tails, 0).customer_by_id
    assert key not in route_observation(p.observation, tails, 1).customer_by_id
    assert key not in route_observation(p.observation, tails).customer_by_id


@pytest.mark.parametrize("algorithm", ["GREEDY", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"])
@pytest.mark.parametrize("dynamicity", [0, .5])
@pytest.mark.parametrize("insertion", [False, True])
def test_continuity_runs_are_auditable_and_repeatable(algorithm, dynamicity, insertion):
    config = simulation_config(dict(algorithm=algorithm, fleet_mode="lazy_reserve", route_continuity=True,
                                    route_insertion=insertion, require_root_coverage=True,
                                    max_idle_wait=10, mcts_iterations=32))
    instance, _, scenario, _ = prepare("c101C5", dict(dynamicity=dynamicity))
    a = EventDrivenSimulator(instance, scenario, config).run()
    b = EventDrivenSimulator(instance, scenario, config).run()
    assert a.logical_dict() == b.logical_dict()
    assert all(audit_result(a, instance, scenario).values())
    assert a.metrics["customers_served"] == 5


@pytest.mark.parametrize("algorithm", ["INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"])
def test_two_known_customers_use_one_executable_route_without_wait_loops(algorithm):
    base = synthetic(release=0)
    config = simulation_config(dict(algorithm=algorithm, fleet_mode="lazy_reserve", route_continuity=True,
                                    require_root_coverage=True, max_idle_wait=10, mcts_iterations=32))
    result = EventDrivenSimulator(base.instance, base.scenario, config).run()
    assert result.metrics["customers_served"] == 2
    assert result.metrics["vehicles_activated"] == 1
    assert result.metrics["wait_selected"] == 0
    assert all(audit_result(result, base.instance, base.scenario).values())


@pytest.mark.parametrize("insertion", [False, True])
def test_continuity_never_observes_hidden_geometry(insertion):
    base = synthetic(release=30)
    altered = replace(base.instance, customers=(base.instance.customers[0],
                      replace(base.instance.customers[1], x=3)))
    config = simulation_config(dict(fleet_mode="lazy_reserve", route_continuity=True, route_insertion=insertion,
                                    require_root_coverage=True, max_idle_wait=10, mcts_iterations=32))
    a = EventDrivenSimulator(base.instance, base.scenario, config).run()
    b = EventDrivenSimulator(altered, base.scenario, config).run()
    assert [d for d in a.decisions if d["time"] < 30] == [d for d in b.decisions if d["time"] < 30]
    assert a.metrics["customers_served"] == b.metrics["customers_served"] == 2


def test_continuity_rejects_incompatible_modes():
    with pytest.raises(ValueError, match="lazy reserve"):
        simulation_config(dict(route_continuity=True))
    with pytest.raises(ValueError, match="summary trace"):
        simulation_config(dict(route_continuity=True, fleet_mode="lazy_reserve", trace_level="none"))
    with pytest.raises(ValueError, match="requires route continuity"):
        simulation_config(dict(route_insertion=True))


@pytest.mark.parametrize("algorithm", ["GREEDY", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"])
def test_released_customer_inserted_after_nonpreemptible_busy_action(algorithm):
    base = synthetic(release=5)
    config = simulation_config(dict(algorithm=algorithm, fleet_mode="lazy_reserve", route_continuity=True,
                                    route_insertion=True, require_root_coverage=True, max_idle_wait=10,
                                    mcts_iterations=32))
    result = EventDrivenSimulator(base.instance, base.scenario, config).run()
    assert result.metrics["customers_served"] == 2
    assert result.metrics["vehicles_activated"] == 1
    assert result.metrics["route_insertions"] == 1
    first = next(s for s in result.steps if s.served == "A")
    assert first.before.time == 0 and first.after.time == 25
    assert next(d for d in result.decisions if d["time"] == 5)["route_insertions"] == [dict(vehicle_id=0, customer="B")]
    assert all(audit_result(result, base.instance, base.scenario).values())


def test_insertion_cannot_depart_from_a_stale_idle_state():
    from evrp.continuity import insert_known_requests
    p = problem(max_idle_wait=10)
    action = next(a for a in p.actions(p.initial) if a.kind == "serve")
    state, _ = p.predict(p.initial, action)
    observation = replace(p.observation, time=state.vehicle.time + 1,
                          customers=tuple(c for c in p.observation.customers if c.id != action.destination))
    tails = {}
    assert insert_known_requests({0: state.vehicle}, {}, observation, p.config, tails) == []
    assert tails == {}

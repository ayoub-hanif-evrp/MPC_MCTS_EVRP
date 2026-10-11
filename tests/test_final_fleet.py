from dataclasses import replace
from copy import deepcopy

import pytest

from evrp.experiments import prepare, simulation_config, audit_result, results_path
from evrp.model import Action
from evrp.simulator import EventDrivenSimulator
from evrp.storage import canonical, save_json, load_json
from tests.test_simulator import synthetic


@pytest.mark.parametrize("name", ["c101C5", "r104C5", "rc105C5"])
@pytest.mark.parametrize("dod", [0., .5])
@pytest.mark.parametrize("algorithm", ["GREEDY", "RH_REGRET", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"])
def test_fixed_fleet_end_to_end(name, dod, algorithm):
    cfg = dict(algorithm=algorithm, dynamicity=dod, mcts_iterations=8)
    instance, reference, scenario, _ = prepare(name, cfg)
    sim = EventDrivenSimulator(instance, scenario, simulation_config(cfg))
    result = sim.run()
    assert set(sim.state.vehicles) == set(range(reference.fleet_size))
    assert result.metrics["vehicles_activated"] <= reference.fleet_size
    assert all(audit_result(result, instance, scenario).values())
    assert result.effective_config["route_continuity"] and result.effective_config["regret_repair"]
    canonical(result)  # Unique-insertion priority must be serializable JSON.


def test_unused_ev_not_activated_and_busy_suffix_maintained():
    base = synthetic(release=5, fleet=2)
    cfg = simulation_config(dict(algorithm="RH_REGRET"))
    sim = EventDrivenSimulator(base.instance, base.scenario, cfg)
    result = sim.run()
    assert result.metrics["customers_served"] == 2
    assert result.metrics["vehicles_activated"] == 1
    first = next(s for s in result.steps if s.served == "A")
    assert first.before.time == 0 and first.after.time == 25
    assert all(audit_result(result, base.instance, base.scenario).values())
    altered = deepcopy(result)
    decision = next(d for d in altered.decisions if d["route_insertions"])
    decision["route_insertions"][0]["vehicle_id"] = 99
    with pytest.raises(AssertionError, match="owner"):
        audit_result(altered, base.instance, base.scenario)


def test_hidden_geometry_cannot_change_pre_release_policy():
    base = synthetic(release=30)
    changed = replace(base.instance, customers=(base.instance.customers[0], replace(base.instance.customers[1], x=3)))
    cfg = simulation_config(dict(mcts_iterations=8))
    a = EventDrivenSimulator(base.instance, base.scenario, cfg).run()
    b = EventDrivenSimulator(changed, base.scenario, cfg).run()
    assert [d for d in a.decisions if d["time"] < 30] == [d for d in b.decisions if d["time"] < 30]


def test_ready_suffix_is_a_feasible_incumbent_not_a_permanent_reservation():
    from evrp.continuity import route_observation, with_soft_incumbent
    from evrp.mcts import MCTSOptimizer
    from tests.test_planning import problem
    p = problem(iterations=8)
    r = MCTSOptimizer().solve(p, 0)
    old_route = next(p.actions for p in r.proposals if p.first.kind == "serve")
    updated = with_soft_incumbent(r, p.current_state, p.observation, p.config, old_route)
    assert old_route in [candidate.actions for candidate in updated.candidates]
    assert r.proposals == updated.proposals[:len(r.proposals)]
    other = route_observation(p.observation, {})
    assert set(a.destination for a in old_route if a.kind == "serve") <= set(other.customer_by_id)
    assert with_soft_incumbent(r, p.current_state, p.observation, p.config,
                               (Action("serve", "HIDDEN"),)) == r


def test_coordinator_can_reassign_old_future_customer_to_another_ev():
    from evrp.continuity import with_soft_incumbent
    from evrp.coordinator import coordinate
    from evrp.mpc import PlanningResult
    from evrp.repair import route_proposal
    from evrp.simulator import idle_proposal
    from tests.test_repair import customer, serves, setup
    first, obs, config = setup((customer("A", -10), customer("B", 10)))
    second = replace(first, id=1, location=obs.customer_by_id["B"], departed=True)
    old = serves("A", "B")
    a = route_proposal(first, serves("A"), obs, config)
    b = route_proposal(second, serves("B"), obs, config)
    first_plan = with_soft_incumbent(PlanningResult((a,), idle_proposal(first, obs, config)),
                                     first, obs, config, old)
    second_plan = PlanningResult((b,), idle_proposal(second, obs, config))
    assert old in [p.actions for p in first_plan.candidates]
    chosen = coordinate({0: first_plan.candidates, 1: second_plan.candidates},
                        available=frozenset({"A", "B"}))
    assert chosen[0].predicted_customer_sequence == ("A",)
    assert chosen[1].predicted_customer_sequence == ("B",)


def test_busy_action_stays_committed_while_only_its_future_tail_is_frozen():
    from evrp.continuity import route_observation
    from evrp.model import Observation, transition
    from tests.test_repair import customer, setup, serves
    state, obs, _ = setup((customer("BUSY", 1), customer("FUTURE", 2), customer("FREE", 3)))
    action = transition(state, Action("serve", "BUSY"), obs)
    observed = replace(obs, committed_customers=(("BUSY", 0),))
    masked = route_observation(observed, {0: serves("FUTURE")}, 1)
    assert action.action == Action("serve", "BUSY")
    assert action.after.current_committed_action is None
    assert "BUSY" in masked.committed_ids
    assert "FUTURE" not in masked.customer_by_id
    assert "FREE" in masked.customer_by_id


def test_repair_is_after_coordination_and_not_iterated(monkeypatch):
    import evrp.simulator as simulator
    import evrp.repair as repair
    order = []
    coordinate, insert = simulator.coordinate, repair.regret_repair
    def coordination(*args, **kwargs):
        order.append("coordinate")
        return coordinate(*args, **kwargs)
    def repairing(*args, **kwargs):
        assert order[-1] == "coordinate"
        order.append("repair")
        return insert(*args, **kwargs)
    monkeypatch.setattr(simulator, "coordinate", coordination)
    monkeypatch.setattr(repair, "regret_repair", repairing)
    base = synthetic(release=0)
    result = EventDrivenSimulator(base.instance, base.scenario, simulation_config(dict(mcts_iterations=8))).run()
    assert order == [name for _ in result.decisions for name in ("coordinate", "repair")]


def test_no_external_research_writes(tmp_path):
    with pytest.raises(ValueError, match="results"):
        results_path("../outside")
    with pytest.raises(ValueError, match="results"):
        save_json("docs/not_a_result.json", {})
    p = tmp_path / "storage.json.gz"
    save_json(p, dict(rows=[1, 2, 3]))
    assert load_json(p) == dict(rows=[1, 2, 3])


def test_full_and_summary_traces_preserve_persistent_execution():
    base = synthetic(release=5)
    cfg = simulation_config(dict(mcts_iterations=8))
    full = EventDrivenSimulator(base.instance, base.scenario, cfg).run()
    compact = EventDrivenSimulator(base.instance, base.scenario, replace(cfg, trace_level="summary")).run()
    assert full.steps == compact.steps and full.events == compact.events

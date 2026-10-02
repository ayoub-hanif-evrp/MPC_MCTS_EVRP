from dataclasses import replace

import pytest

from evrp.coordinator import coordinate
from evrp.instance import load_instance
from evrp.mcts import MCTSOptimizer, Node, uct
from evrp.model import Action, Observation
from evrp.mpc import MPCConfig, MPCController, MPCPlanningProblem, MPCProposal
from evrp.reference import initial_vehicle
from evrp.storage import BENCHMARK


def problem(horizon=3, **kwargs):
    instance = load_instance(BENCHMARK / "c101C5.txt")
    return MPCPlanningProblem(Observation(0, instance.infrastructure, instance.customers),
                              initial_vehicle(instance), MPCConfig(prediction_horizon=horizon, **kwargs))


def test_control_horizon_fixed():
    with pytest.raises(ValueError, match="Control horizon"):
        MPCConfig(control_horizon=2)


@pytest.mark.parametrize("horizon", [1, 3, 5, 8])
def test_mcts_horizon_and_reproducibility(horizon):
    p = problem(horizon, iterations=4, top_l=5)
    a, b = MCTSOptimizer().solve(p, 13), MCTSOptimizer().solve(p, 13)
    assert a.proposals == b.proposals
    assert a.statistics.iterations == 4
    assert len({x.first for x in a.proposals}) == len(a.proposals)
    for candidate in a.proposals:
        assert len(candidate.predicted_customer_sequence) <= horizon
        assert candidate.cost == pytest.approx(candidate.predicted_distance + p.terminal_cost(
            replace(p.initial, vehicle=candidate.predicted_end_state)))
        assert all(a.destination in {c.id for c in p.observation.customers}
                   for a in candidate.actions if a.kind == "serve")
    if horizon == 1:
        assert all(len(c.predicted_customer_sequence) <= 1 for c in a.proposals)
    else:
        assert any(len(c.predicted_customer_sequence) > 1 for c in a.proposals)


def test_uct_unvisited_and_reward_sign():
    root = Node(problem().initial)
    assert uct(root, 1, 1.4) == float("inf")
    root.visits, root.value_sum = 2, -20
    assert uct(root, 1, 0) == -10


def test_actions_feasible_and_candidate_bound():
    p = problem(candidate_limit=2)
    actions = p.actions(p.initial)
    assert sum(a.kind == "serve" for a in actions) <= 2
    for action in actions:
        p.predict(p.initial, action)


def test_wall_clock_budget_terminates():
    result = MCTSOptimizer().solve(problem(budget_mode="wall_clock", time_limit=0.001), 1)
    assert result.statistics.iterations >= 1
    assert result.statistics.elapsed < 10


def test_new_mpc_problem_after_feedback():
    p = problem()
    controller = MPCController(p.config)
    first = controller.formulate(p.current_state, p.observation)
    action = next(a for a in first.actions(first.initial) if a.kind == "serve")
    state, _ = first.predict(first.initial, action)
    observation = replace(p.observation, time=state.vehicle.time,
                          customers=tuple(c for c in p.observation.customers if c.id != action.destination))
    second = controller.formulate(state.vehicle, observation)
    assert first is not second
    assert second.current_state != first.current_state
    assert action.destination not in second.initial.remaining


def test_hidden_customer_never_reaches_search_or_terminal(monkeypatch):
    p = problem(iterations=5)
    hidden = p.observation.customers[-1].id
    p = replace(p, observation=replace(p.observation, customers=p.observation.customers[:-1]))
    original = MPCPlanningProblem.terminal_cost
    calls = []
    def checked(self, state):
        assert hidden not in state.remaining
        assert hidden not in {c.id for c in self.observation.customers}
        calls.append(state)
        return original(self, state)
    monkeypatch.setattr(MPCPlanningProblem, "terminal_cost", checked)
    result = MCTSOptimizer().solve(p, 9)
    assert calls
    assert all(hidden not in candidate.predicted_customer_sequence for candidate in result.candidates)


def proposal(*customers, cost=1):
    return MPCProposal(tuple(Action("serve", c) for c in customers), cost)


def test_coordinator_conflicts_and_tail_intentions():
    wait = MPCProposal((Action("wait", wait_duration=1),), 10)
    selected = coordinate({0: (proposal("A", "B"), wait), 1: (proposal("A"), proposal("B", "A", cost=2), wait)})
    assert {p.first.destination for p in selected.values()} == {"A", "B"}
    assert selected[0].actions[1].destination == "B"


def test_noncustomer_actions_do_not_conflict():
    charge = MPCProposal((Action("charge", "S", 10),), 1)
    selected = coordinate({0: (charge,), 1: (charge,)})
    assert len(selected) == 2


def test_wait_fallback_and_existing_commitment():
    wait = MPCProposal((Action("wait", wait_duration=1),), 10)
    selected = coordinate({0: (proposal("A"), wait), 1: (proposal("A"), wait)}, frozenset({"A"}))
    assert all(p.first.kind == "wait" for p in selected.values())


@pytest.mark.parametrize("limit", [1, 3, 5])
def test_top_l_with_separate_fallback(limit):
    result = MCTSOptimizer().solve(problem(iterations=4, top_l=limit), 7)
    assert len(result.proposals) <= limit
    assert result.fallback.first.kind != "serve"


def test_full_charge_targets():
    p = problem(charging_mode="full")
    for action in p.actions(p.initial):
        if action.kind == "charge":
            assert action.target_battery == p.observation.infrastructure.parameters.battery

from dataclasses import replace
from math import isfinite
import random

import pytest

import evrp.mcts as mcts
from evrp.instance import Infrastructure, Location, Parameters
from evrp.model import Action, Observation, VehicleState, escape
from evrp.mpc import MPCConfig, MPCPlanningProblem, proposal_key


def problem(**kwargs):
    depot = Location("D0", "d", 0, 0, 0, 0, 500, 0)
    customers = tuple(Location(name, "c", i, 0, 1, 0, 400, 1)
                      for i, name in enumerate("ABCDEFG", start=1))
    infrastructure = Infrastructure(depot, (), Parameters(100, 20, 1, 1, 1))
    return MPCPlanningProblem(Observation(0, infrastructure, customers),
                              VehicleState(0, depot, 0, 100, 20), MPCConfig(**kwargs))


def assert_feasible(p, proposal):
    replay = p.proposal(proposal.actions, proposal.visits)
    assert replace(replay, mcts_value_estimate=proposal.mcts_value_estimate) == proposal
    assert isfinite(proposal.cost)
    assert proposal.predicted_service_count <= p.config.prediction_horizon
    assert set(proposal.unique_predicted_customer_set) <= p.initial.remaining
    safe = escape(proposal.predicted_end_state, p.observation.infrastructure)
    assert safe is not None
    assert safe.completion <= p.observation.infrastructure.depot.due


def test_proposal_selection_default_and_validation():
    assert MPCConfig().proposal_selection == "quality"
    with pytest.raises(ValueError, match="proposal selection"):
        MPCConfig(proposal_selection="weighted")


@pytest.mark.parametrize("selection", ["quality", "coverage_diverse"])
@pytest.mark.parametrize("horizon", [1, 3, 5])
def test_seeded_selection_horizon_and_distinct_roots(selection, horizon):
    options = dict(proposal_selection=selection, prediction_horizon=horizon,
                   iterations=20, top_l=4, require_root_coverage=True)
    p = problem(**options)
    result = mcts.MCTSOptimizer().solve(p, 19)
    repeated = mcts.MCTSOptimizer().solve(problem(**options), 19)
    assert result.proposals == repeated.proposals
    assert result.evaluated_proposals == repeated.evaluated_proposals
    assert result.statistics.root_actions == repeated.statistics.root_actions
    assert result.statistics.iterations == 20
    assert len(result.proposals) == 4
    assert len({candidate.first for candidate in result.evaluated_proposals}) == len(result.evaluated_proposals)
    assert result.proposals[0] == min(result.evaluated_proposals, key=proposal_key)
    if selection == "quality":
        assert result.proposals == result.evaluated_proposals[:4]
    else:
        remaining = list(result.evaluated_proposals)
        covered = set()
        for candidate in result.proposals:
            expected = min(remaining, key=lambda q: (
                -len(set(q.unique_predicted_customer_set) - covered), proposal_key(q)))
            assert candidate == expected
            remaining.remove(candidate)
            covered.update(candidate.unique_predicted_customer_set)
    assert max(q.predicted_service_count for q in result.proposals) == horizon
    for candidate in result.candidates:
        assert_feasible(p, candidate)
    assert result.statistics.deadline_policy == "none"
    assert not result.statistics.deadline_exceeded
    assert result.statistics.deadline_overrun_seconds == 0


def test_diversity_expected_coverage_and_quality_ties():
    p = problem(prediction_horizon=3)
    routes = [p.proposal(tuple(Action("serve", c) for c in route))
              for route in ("ABC", "BAC", "DE", "ED", "FG", "GF")]
    diverse_config = replace(p.config, proposal_selection="coverage_diverse")
    expected = (routes[0], routes[2], routes[4])
    for seed in range(5):
        shuffled = list(routes)
        random.Random(seed).shuffle(shuffled)
        quality = mcts._select_proposals(shuffled, p.config)
        diverse = mcts._select_proposals(shuffled, diverse_config)
        assert quality == (routes[0], routes[1], routes[2])
        assert diverse == expected
        assert set().union(*(set(q.unique_predicted_customer_set) for q in diverse)) == set("ABCDEFG")
        assert mcts._select_proposals(shuffled, replace(diverse_config, top_l=1)) == (routes[0],)
        assert len(mcts._select_proposals(shuffled, replace(diverse_config, top_l=10))) == len(routes)
    for candidate in routes:
        assert_feasible(p, candidate)


def test_diversity_does_not_change_search_or_evaluated_candidates():
    p = problem(iterations=20, require_root_coverage=True)
    quality = mcts.MCTSOptimizer().solve(p, 7)
    diverse = mcts.MCTSOptimizer().solve(
        replace(p, config=replace(p.config, proposal_selection="coverage_diverse")), 7)
    assert quality.evaluated_proposals == diverse.evaluated_proposals
    assert quality.statistics.root_actions == diverse.statistics.root_actions
    assert quality.fallback == diverse.fallback


def test_iteration_mode_covers_every_root_once_before_uct(monkeypatch):
    p = problem(iterations=1, require_root_coverage=True)
    root_count = len(p.actions(p.initial))
    original_uct, calls = mcts.uct, []

    def checked_uct(child, parent_visits, coefficient):
        assert parent_visits >= root_count
        calls.append(parent_visits)
        return original_uct(child, parent_visits, coefficient)

    monkeypatch.setattr(mcts, "uct", checked_uct)
    result = mcts.MCTSOptimizer().solve(p, 3)
    stats = result.statistics
    assert stats.iterations == stats.root_actions_evaluated == stats.root_action_count == root_count
    assert stats.minimum_root_visits == 1
    assert stats.fraction_root_actions_evaluated == 1
    assert not calls
    extra = mcts.MCTSOptimizer().solve(replace(p, config=replace(p.config, iterations=root_count + 1)), 3)
    assert calls
    assert extra.statistics.iterations == root_count + 1
    assert sum(row["visits"] for row in extra.statistics.root_actions) == root_count + 1


@pytest.mark.parametrize("selection", ["quality", "coverage_diverse"])
@pytest.mark.parametrize("require_coverage", [False, True])
def test_tiny_wall_budget_returns_feasible_incumbent_without_forced_coverage(selection, require_coverage):
    p = problem(budget_mode="wall_clock", time_limit=1e-12,
                proposal_selection=selection, require_root_coverage=require_coverage)
    result = mcts.MCTSOptimizer().solve(p, 0)
    stats = result.statistics
    assert stats.root_action_count > 1
    assert stats.iterations == stats.root_actions_evaluated == stats.nodes_expanded == 0
    assert stats.minimum_root_visits == 0
    assert stats.fraction_root_actions_evaluated == 0
    assert result.evaluated_proposals == ()
    assert result.candidates == (result.fallback,)
    assert_feasible(p, result.fallback)
    assert stats.deadline_policy == "cooperative"
    assert stats.deadline_exceeded
    assert stats.deadline_overrun_seconds == pytest.approx(stats.elapsed - p.config.time_limit)


@pytest.mark.parametrize("expire_at_depth", [0, 1])
def test_cooperative_expiry_during_action_generation(monkeypatch, expire_at_depth):
    p = problem(budget_mode="wall_clock", time_limit=0.01, require_root_coverage=True)
    now = [0.0]
    original = MPCPlanningProblem.actions

    def delayed_actions(self, state):
        actions = original(self, state)
        if state.service_depth == expire_at_depth:
            now[0] = 0.02
        return actions

    monkeypatch.setattr(mcts, "perf_counter", lambda: now[0])
    monkeypatch.setattr(MPCPlanningProblem, "actions", delayed_actions)
    result = mcts.MCTSOptimizer().solve(p, 0)
    stats = result.statistics
    assert stats.iterations == stats.root_actions_evaluated == expire_at_depth
    assert stats.nodes_expanded == expire_at_depth
    assert sum(row["visits"] for row in stats.root_actions) == stats.iterations
    assert stats.root_actions_evaluated < stats.root_action_count
    assert stats.fraction_root_actions_evaluated == pytest.approx(expire_at_depth / stats.root_action_count)
    assert stats.minimum_root_visits == 0
    assert stats.deadline_exceeded
    assert stats.deadline_policy == "cooperative"
    assert stats.elapsed == 0.02
    assert stats.deadline_overrun_seconds == 0.01
    if expire_at_depth:
        assert len(result.proposals) == 1
        assert result.proposals[0].predicted_service_count == 1
        assert result.proposals[0].root_visits == 1
    for candidate in result.candidates:
        assert_feasible(p, candidate)

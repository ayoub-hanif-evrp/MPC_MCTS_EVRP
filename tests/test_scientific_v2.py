from dataclasses import replace

import pytest

from evrp.experiments import prepare, simulation_config, audit_result
from evrp.mcts import MCTSOptimizer
from evrp.model import Action, Observation, transition, InfeasibleAction
from evrp.mpc import MPCPlanningProblem
from evrp.oracle import oracle_reference
from evrp.simulator import EventDrivenSimulator


@pytest.mark.parametrize("mode", ["iterations", "wall_clock"])
def test_mandatory_root_coverage_charged_to_actual_simulations(mode):
    from tests.test_planning import problem
    p = problem(iterations=1, budget_mode=mode, time_limit=1e-9, require_root_coverage=True)
    result = MCTSOptimizer().solve(p, 0)
    s = result.statistics
    assert s.root_action_count > 1
    assert s.root_action_count == s.root_actions_evaluated == s.iterations
    assert s.minimum_root_visits == 1
    assert s.fraction_root_actions_evaluated == 1


@pytest.mark.parametrize("algorithm", ["GREEDY", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"])
def test_lazy_reserve_is_not_instantiated_until_selected_and_audits(algorithm):
    config = dict(algorithm=algorithm, fleet_mode="lazy_reserve", require_root_coverage=True,
                  max_idle_wait=10, mcts_iterations=32, dynamicity=.5, diagnostics=True)
    instance, _, scenario, _ = prepare("c101C5", config)
    sim = EventDrivenSimulator(instance, scenario, simulation_config(config))
    assert sim.state.vehicles == sim.agents == {}
    result = sim.run()
    assert len(sim.agents) == result.metrics["vehicles_activated"] <= len(instance.customers)
    assert all(audit_result(result, instance, scenario).values())
    assert len(result.diagnostics["unserved"]) == result.metrics["customers_unserved"]
    assert all(s["minimum_root_visits"] >= 1 for s in result.searches if s["root_action_count"])


def test_diagnostics_do_not_change_policy():
    config = dict(fleet_mode="lazy_reserve", require_root_coverage=True, max_idle_wait=10,
                  mcts_iterations=8, dynamicity=.5)
    instance, _, scenario, _ = prepare("c101C5", config)
    a = EventDrivenSimulator(instance, scenario, simulation_config(config)).run()
    b = EventDrivenSimulator(instance, scenario, simulation_config({**config, "diagnostics": True})).run()
    assert a.steps == b.steps and a.events == b.events


def test_reserve_survives_until_future_release():
    from tests.test_simulator import synthetic
    base = synthetic(release=30)
    config = replace(base.config, fleet_mode="lazy_reserve",
                     mpc=replace(base.config.mpc, require_root_coverage=True, max_idle_wait=10, iterations=8))
    result = EventDrivenSimulator(base.instance, base.scenario, config).run()
    assert result.metrics["customers_served"] == 2
    assert all(audit_result(result, base.instance, base.scenario).values())


def test_bounded_wait_and_permanent_single_tour_return():
    from tests.test_planning import problem
    p = problem(max_idle_wait=10)
    assert p.fallback(p.initial).wait_duration <= 10
    serving = next(a for a in p.actions(p.initial) if a.kind == "serve")
    s, _ = p.predict(p.initial, serving)
    empty = replace(p, observation=replace(p.observation, customers=()), current_state=s.vehicle)
    action = empty.fallback(empty.initial)
    assert action.kind in {"return", "charge"}
    returned = transition(p.current_state, Action("return", p.current_state.location.id), p.observation)
    with pytest.raises(InfeasibleAction):
        transition(returned.after, serving, p.observation)


def test_offline_oracle_and_incompatible_release_rejected():
    config = dict(dynamicity=.5)
    i, r, s, _ = prepare("c101C5", config)
    result = oracle_reference(i, r, s, config)
    assert result.metrics["customers_served"] == 5
    assert result.metadata["policy_role"] == "offline feasibility oracle"
    assert all(audit_result(result, i, s).values())
    first = next(t for route in r.routes for t in route.steps if t.served)
    bad = replace(s, customer_release_times=tuple((c, first.before.time+1 if c == first.served else t)
                                                  for c, t in s.customer_release_times))
    with pytest.raises(ValueError, match="precedes"):
        oracle_reference(i, r, bad, config)


def test_v1_disk_audit_still_valid():
    from evrp.audit import audit_record
    from evrp.storage import load_json, ROOT
    path = next((ROOT / "results/paper_v1_fixed_fleet/raw").glob("*.json.gz"))
    assert audit_record(load_json(path)) == []


def test_busy_forecast_prevents_redundant_reserve_activation():
    from tests.test_planning import problem
    from evrp.coordinator import coordinate
    from evrp.reserve import bind_proposal
    p = problem(max_idle_wait=10)
    a = next(a for a in p.actions(p.initial) if a.kind == "serve")
    new = bind_proposal(p.proposal((a,)), -1)
    idle = bind_proposal(p.proposal((p.fallback(p.initial),)), -1)
    selected = coordinate({-1: (new, idle)}, available=frozenset({a.destination}),
                          reserve_ids=frozenset({-1}), reserve_count=10,
                          background_intents=frozenset({a.destination}))
    assert selected[-1].first.kind == "wait"


def test_full_paper_execution_is_blocked_pending_scientific_review(tmp_path):
    from evrp.paper import execute_paper
    with pytest.raises(RuntimeError, match="scientific review"):
        execute_paper({}, tmp_path, execute=True)


def test_reserve_planning_cannot_depend_on_hidden_customer_geometry():
    from tests.test_simulator import synthetic
    base = synthetic(release=30)
    altered = replace(base.instance, customers=(base.instance.customers[0],
                      replace(base.instance.customers[1], x=3)))
    config = simulation_config(dict(fleet_mode="lazy_reserve", require_root_coverage=True,
                                    max_idle_wait=10, mcts_iterations=8))
    a = EventDrivenSimulator(base.instance, base.scenario, config).run()
    b = EventDrivenSimulator(altered, base.scenario, config).run()
    assert [d for d in a.decisions if d["time"] < 30] == [d for d in b.decisions if d["time"] < 30]


def test_v2_presentation_uses_only_nonempty_measured_figures():
    from evrp.storage import ROOT
    import pandas as pd
    root = ROOT / "results/paper_v2"
    figures = list((root/"figures").rglob("*.png"))
    assert len(figures) == 7
    for png in figures:
        assert png.with_suffix(".pdf").exists()
        assert len(pd.read_csv(png.with_name(png.stem+"_data.csv"))) > 0
    frame = pd.read_csv(root/"tables/csv/main_by_family.csv")
    assert set(frame.Algorithm) == {"Greedy", "Independent", "Coordinated"}
    pairs = pd.read_csv(root/"tables/csv/paired_methods.csv")
    assert pairs.loc[~(pairs.equal_service & pairs.equal_EVs), "Delta_distance"].isna().all()

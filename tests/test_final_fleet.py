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


def test_retained_infeasible_commitment_cannot_disappear():
    from evrp.continuity import preserve_continuation
    from evrp.mcts import MCTSOptimizer
    from tests.test_planning import problem
    p = problem(iterations=8)
    r = MCTSOptimizer().solve(p, 0)
    with pytest.raises(RuntimeError, match="cannot be discarded"):
        preserve_continuation(r, p.current_state, p.observation, p.config, (Action("serve", "HIDDEN"),))


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

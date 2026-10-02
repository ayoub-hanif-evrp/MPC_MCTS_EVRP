from dataclasses import replace

import pytest

from evrp.instance import Infrastructure, Instance, Location, Parameters, load_instance
from evrp.model import Action
from evrp.mpc import MPCConfig, MPCPlanningProblem, PlanningResult
from evrp.reference import ReferenceConfig, solve_reference
from evrp.scenario import DynamicScenario, METHOD, generate
from evrp.simulator import EventDrivenSimulator, SimulationConfig
from evrp.storage import BENCHMARK


class ScriptAgent:
    def __init__(self):
        self.calls = []

    def plan(self, state, observation, seed):
        self.calls.append((state.time, tuple(c.id for c in observation.customers)))
        problem = MPCPlanningProblem(observation, state, MPCConfig(prediction_horizon=3))
        customers = list(observation.customers)
        fallback = problem.proposal((problem.fallback(problem.initial),))
        if customers:
            action = Action("serve", customers[0].id)
            return PlanningResult((problem.proposal((action,)),), fallback)
        return PlanningResult((), fallback)


def synthetic(release=5, fleet=1):
    depot = Location("D", "d", 0, 0, 0, 0, 100, 0)
    customers = (Location("A", "c", 1, 0, 1, 20, 50, 5),
                 Location("B", "c", 2, 0, 1, 30, 80, 5))
    instance = Instance("c101toy", "test", Infrastructure(depot, (), Parameters(100, 10, 1, 1, 1)), customers)
    scenario = DynamicScenario(instance.name, instance.sha256, METHOD, "exact_count", 0.5,
                                0.5 if release else 0, 0, "test", fleet,
                                (("A", 0), ("B", release)), (("A", 0), ("B", 30)), 1, 1)
    sim = EventDrivenSimulator(instance, scenario, SimulationConfig(algorithm="INDEPENDENT_MPC_MCTS"))
    sim.agents = {k: ScriptAgent() for k in sim.agents}
    return sim


def test_busy_vehicle_waiting_for_window_not_interrupted():
    sim = synthetic()
    result = sim.run()
    assert result.metrics["customers_served"] == 2
    assert result.metrics["final_return_feasibility"]
    assert not any(0 < time < 25 for time, _ in sim.agents[0].calls)
    first = next(s for s in result.steps if s.served == "A")
    assert first.before.time == 0 and first.after.time == 25
    assert any(e.time == 5 and e.kind == "release" for e in result.events)


def test_idle_vehicle_wakes_at_release():
    sim = synthetic(fleet=2)
    result = sim.run()
    assert any(time == 5 and "B" in ids for time, ids in sim.agents[1].calls)
    assert result.metrics["customers_served"] == 2


def test_simultaneous_release_and_completion():
    sim = synthetic(release=25)
    result = sim.run()
    decision = next(d for d in result.decisions if d["time"] == 25)
    assert decision["available"] == ["B"]
    assert decision["committed_before"] == {}
    assert sim.state.served_customers == {"A", "B"}


@pytest.mark.parametrize("algorithm", ["GREEDY", "MPC_MCTS_H1", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"])
def test_reproducible_sequential_run(algorithm):
    instance = load_instance(BENCHMARK / "c101C5.txt")
    reference = solve_reference(instance, ReferenceConfig(multistarts=1))
    scenario = generate(instance, reference, 2, 0.5)
    config = SimulationConfig(algorithm=algorithm, mpc=MPCConfig(iterations=2, prediction_horizon=3))
    a = EventDrivenSimulator(instance, scenario, config).run()
    b = EventDrivenSimulator(instance, scenario, config).run()
    assert a.logical_dict() == b.logical_dict()
    assert a.metrics["final_return_feasibility"]
    assert a.metrics["battery_violations"] == a.metrics["capacity_violations"] == a.metrics["time_window_violations"] == 0
    releases = dict(scenario.customer_release_times)
    for decision in a.decisions:
        assert all(releases[c] <= decision["time"] for c in decision["available"])


def test_parallel_same_logical_decisions():
    instance = load_instance(BENCHMARK / "rc105C5.txt")
    reference = solve_reference(instance, ReferenceConfig(multistarts=1))
    scenario = generate(instance, reference, 0)
    config = SimulationConfig(mpc=MPCConfig(iterations=1, prediction_horizon=1))
    a = EventDrivenSimulator(instance, scenario, config).run()
    b = EventDrivenSimulator(instance, scenario, replace(config, parallel_agents=True)).run()
    assert a.logical_dict() == b.logical_dict()


@pytest.mark.parametrize("mode", ["full", "partial"])
def test_charging_mode_end_to_end(mode):
    instance = load_instance(BENCHMARK / "r104C5.txt")
    reference = solve_reference(instance, ReferenceConfig(multistarts=1))
    scenario = generate(instance, reference, 0)
    config = SimulationConfig(algorithm="GREEDY", mpc=MPCConfig(charging_mode=mode))
    result = EventDrivenSimulator(instance, scenario, config).run()
    charges = [s for s in result.steps if s.action.kind == "charge"]
    assert charges
    assert result.metrics["final_return_feasibility"]
    if mode == "full":
        assert all(s.after.battery == instance.infrastructure.parameters.battery for s in charges)
    else:
        assert any(s.after.battery < instance.infrastructure.parameters.battery for s in charges)

"""Event-triggered, non-preemptive plant execution with interruptible idle waits."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from time import perf_counter

import numpy as np

from .agent import EVAgent, agent_seed
from .baselines import greedy_plan, independent_selection
from .coordinator import coordinate
from .instance import Instance
from .model import Action, EPS, Observation, Transition, transition
from .mpc import MPCConfig, PlanningResult
from .observation import get_agent_observation, initial_global_state
from .scenario import DynamicScenario
from .storage import save_json

ALGORITHMS = {"GREEDY", "MPC_MCTS_H1", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"}


@dataclass(frozen=True)
class SimulationConfig:
    algorithm: str = "COORDINATED_MPC_MCTS"
    experiment_seed: int = 0
    parallel_agents: bool = False
    workers: int = 2
    max_events: int = 100000
    mpc: MPCConfig = field(default_factory=MPCConfig)

    def __post_init__(self):
        if self.algorithm not in ALGORITHMS or self.workers < 1 or self.max_events < 1:
            raise ValueError("Invalid simulation configuration")


@dataclass(frozen=True)
class SimulationEvent:
    time: float
    kind: str
    vehicle_id: int | None = None
    customer_id: str | None = None
    action: Action | None = None


@dataclass
class ExperimentResult:
    metadata: dict
    effective_config: dict
    metrics: dict
    events: list[SimulationEvent]
    steps: list[Transition]
    decisions: list[dict]
    searches: list[dict]
    unserved_customers: list[str]

    def save(self, path):
        save_json(path, self)

    def logical_dict(self) -> dict:
        result = asdict(self)
        result["searches"] = [{k: v for k, v in search.items() if k != "elapsed"} for search in result["searches"]]
        result["metrics"] = {k: v for k, v in result["metrics"].items() if "planning_time" not in k}
        result["effective_config"].pop("parallel_agents", None)
        result["effective_config"].pop("workers", None)
        return result


def _plan_job(agent, state, observation, seed, algorithm):
    if algorithm == "GREEDY":
        return greedy_plan(state, observation, agent.controller.config)
    return agent.plan(state, observation, seed)


class EventDrivenSimulator:
    def __init__(self, instance: Instance, scenario: DynamicScenario,
                 config: SimulationConfig = SimulationConfig()):
        self.instance, self.scenario, self.config = instance, scenario, config
        if config.algorithm == "MPC_MCTS_H1":
            self.config = replace(config, mpc=replace(config.mpc, prediction_horizon=1))
        self.state = initial_global_state(instance, scenario)
        self.agents = {k: EVAgent(k, self.config.mpc) for k in self.state.vehicles}

    def run(self) -> ExperimentResult:
        state, instance, config = self.state, self.instance, self.config
        events, steps, decisions, searches, timings = [], [], [], [], []
        epochs = replans = conflicts = resolved = waits = 0
        coverages, new_activations = [], 0
        pool = ProcessPoolExecutor(max_workers=config.workers) if config.parallel_agents else None
        try:
            for _ in range(config.max_events):
                for key in state.reveal():
                    events.append(SimulationEvent(state.time, "release", customer_id=key))
                completed = sorted(k for k, step in state.busy.items() if step.after.time <= state.time)
                for k in completed:
                    step = state.busy.pop(k)
                    state.vehicles[k] = step.after
                    steps.append(step)
                    if step.served:
                        assert state.committed_customers.pop(step.served) == k
                        assert step.served not in state.served_customers
                        state.served_customers.add(step.served)
                    events.append(SimulationEvent(state.time, "complete", k, step.served, step.action))
                # All co-timed releases/completions are processed before any observation.
                state.check_partition(instance)
                ready = [k for k, v in sorted(state.vehicles.items()) if k not in state.busy and not v.finished]
                for k in ready:
                    vehicle = state.vehicles[k]
                    if vehicle.time < state.time:
                        step = transition(vehicle, Action("wait", wait_duration=state.time - vehicle.time),
                                          Observation(vehicle.time, instance.infrastructure, ()))
                        state.vehicles[k] = step.after
                        steps.append(step)
                if not ready and not state.busy:
                    break
                if ready:
                    observation = get_agent_observation(state, instance)
                    started = perf_counter()
                    jobs = [(self.agents[k], state.vehicles[k], observation,
                             agent_seed(config.experiment_seed, self.scenario.scenario_seed, epochs, k),
                             config.algorithm) for k in ready]
                    if pool:
                        futures = [pool.submit(_plan_job, *job) for job in jobs]
                        results = [future.result() for future in futures]
                    else:
                        results = [_plan_job(*job) for job in jobs]
                    plans: dict[int, PlanningResult] = dict(zip(ready, results))
                    firsts = [r.proposals[0].first.destination for r in results
                              if r.proposals and r.proposals[0].first.kind == "serve"]
                    duplicates = len(firsts) - len(set(firsts))
                    conflicts += duplicates
                    if config.algorithm in {"GREEDY", "INDEPENDENT_MPC_MCTS"}:
                        selected, count = independent_selection(plans)
                        resolved += count
                    else:
                        selected = coordinate({k: r.candidates for k, r in plans.items()},
                                              frozenset(state.committed_customers),
                                              available=frozenset(c.id for c in observation.customers))
                        resolved += duplicates
                    timings.append(perf_counter() - started)
                    coverage = set().union(*(set(p.unique_predicted_customer_set) for p in selected.values()))
                    coverages.append(len(coverage))
                    new_activations += sum(p.new_activation for p in selected.values())
                    replans += len(ready)
                    decision = {"epoch": epochs, "time": state.time,
                                "available": [c.id for c in observation.customers],
                                "committed_before": dict(observation.committed_customers),
                                "candidates": {str(k): [asdict(p) for p in r.candidates] for k, r in plans.items()},
                                "unique_intention_coverage": sorted(coverage),
                                "plans": {str(k): asdict(p) for k, p in selected.items()}}
                    decisions.append(decision)
                    for k, result in plans.items():
                        searches.append({"epoch": epochs, "vehicle_id": k, **asdict(result.statistics)})
                    for k, proposal in selected.items():
                        action = proposal.first
                        step = transition(state.vehicles[k], action, observation)
                        events.append(SimulationEvent(state.time, "dispatch", k, step.served, action))
                        if action.kind == "wait":
                            state.idle_until[k] = step.after.time
                            waits += 1
                        else:
                            state.idle_until.pop(k, None)
                            state.busy[k] = step
                            state.vehicles[k] = replace(state.vehicles[k], status="busy", current_committed_action=action)
                            if step.served:
                                assert step.served in state.available_customers
                                state.available_customers.pop(step.served)
                                state.committed_customers[step.served] = k
                    epochs += 1
                    state.check_partition(instance)
                future = [release for _, release in state.hidden_customers.values() if release > state.time]
                future.extend(step.after.time for step in state.busy.values())
                future.extend(time for k, time in state.idle_until.items() if not state.vehicles[k].finished)
                if not future:
                    break
                next_time = min(future)
                if next_time < state.time or next_time > instance.infrastructure.depot.due + EPS:
                    raise RuntimeError("Invalid next event time")
                state.time = next_time
            else:
                raise RuntimeError("Simulation event guard exceeded; possible nonterminating policy")
        finally:
            if pool:
                pool.shutdown(wait=True, cancel_futures=True)
        events.append(SimulationEvent(state.time, "end"))
        served = len(state.served_customers)
        distance = sum(step.distance for step in steps)
        returned = all(v.finished and v.location.kind == "d" for v in state.vehicles.values())
        total = len(instance.customers)
        metrics = {"feasible": served == total and returned, "customers_served": served,
                   "complete_service": served == total,
                   "customers_unserved": total - served, "service_ratio": served / total if total else 1.0,
                   "total_distance": distance, "distance_per_served_customer": distance / served if served else None,
                   "vehicles_activated": sum(v.departed for v in state.vehicles.values()),
                   "total_charging_visits": sum(s.action.kind == "charge" for s in steps),
                   "total_energy_charged": sum(s.energy_charged for s in steps),
                   "total_charging_time": sum(s.charging_time for s in steps),
                   "total_waiting_time": sum(s.waiting_time for s in steps),
                   "final_return_feasibility": returned,
                   "time_window_violations": sum(s.action.kind == "serve" and s.service_start > s.after.location.due + EPS for s in steps),
                   "battery_violations": sum(s.after.battery < -EPS or s.after.battery > instance.infrastructure.parameters.battery + EPS for s in steps),
                   "capacity_violations": sum(s.after.load < -EPS for s in steps),
                   "decision_epochs": epochs, "duplicate_customer_proposal_conflicts": conflicts,
                   "conflicts_resolved": resolved, "wait_selected": waits, "agent_replans": replans,
                   "mean_unique_intention_coverage": float(np.mean(coverages)) if coverages else 0.0,
                   "vehicle_activations_caused_by_coordinator": new_activations if config.algorithm in {"COORDINATED_MPC_MCTS", "MPC_MCTS_H1"} else 0,
                   "duplicate_service_violations": 0, "hidden_information_violations": 0,
                   "mcts_iterations": sum(s["iterations"] for s in searches),
                   "nodes_expanded": sum(s["nodes_expanded"] for s in searches)}
        for name, function in [("mean", np.mean), ("median", np.median), ("p95", lambda x: np.percentile(x, 95)), ("maximum", np.max), ("total", np.sum)]:
            metrics[f"{name}_planning_time"] = float(function(timings)) if timings else 0.0
        import re
        metadata = {"instance": instance.name, "instance_sha256": instance.sha256,
                    "instance_family": re.match(r"([a-z]+[12])", instance.name).group(1).upper(),
                    "number_of_customers": total, "number_of_stations": len(instance.infrastructure.stations),
                    "K": self.scenario.fleet_size, "DoD_target": self.scenario.target_DoD,
                    "DoD_realized": self.scenario.realized_DoD, "scenario_seed": self.scenario.scenario_seed,
                    "scenario_identifier": self.scenario.identifier, "algorithm_seed": config.experiment_seed,
                    "algorithm": config.algorithm, "reference_schedule_identifier": self.scenario.reference_schedule_identifier}
        return ExperimentResult(metadata, asdict(config), metrics, events, steps, decisions, searches,
                                sorted(c.id for c in instance.customers if c.id not in state.served_customers))

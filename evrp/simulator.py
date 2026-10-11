"""Fixed-fleet event-driven MPC with persistent routes and one repair pass."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from time import perf_counter

import numpy as np

from .agent import EVAgent, agent_seed
from .baselines import greedy_plan, independent_selection
from .continuity import (assert_unique_routes, with_soft_incumbent, reserved_customers,
                         route_observation, service_prefix, service_tail)
from .coordinator import coordinate
from .instance import Instance
from .model import Action, EPS, Observation, Transition, transition
from .mpc import MPCConfig, MPCPlanningProblem, PlanningResult
from .observation import get_agent_observation, initial_global_state
from .scenario import DynamicScenario
from .storage import save_json

ALGORITHMS = {"GREEDY", "RH_REGRET", "MPC_MCTS_H1", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"}


@dataclass(frozen=True)
class SimulationConfig:
    algorithm: str = "COORDINATED_MPC_MCTS"
    experiment_seed: int = 0
    parallel_agents: bool = False
    workers: int = 2
    max_events: int = 100000
    mpc: MPCConfig = field(default_factory=MPCConfig)
    trace_level: str = "full"
    symmetry_reuse: bool = False
    fleet_mode: str = "fixed_reference"
    diagnostics: bool = False
    route_continuity: bool = True
    regret_repair: bool = True

    def __post_init__(self):
        if self.algorithm not in ALGORITHMS or self.workers < 1 or self.max_events < 1:
            raise ValueError("Invalid simulation configuration")
        if self.trace_level not in {"none", "summary", "full"}:
            raise ValueError("Unknown trace level")
        if self.fleet_mode != "fixed_reference":
            raise ValueError("Only the fixed K_ref fleet is supported")
        if self.route_continuity and self.trace_level == "none":
            raise ValueError("Route continuity requires at least a summary trace")
        if self.algorithm == "RH_REGRET" and not (self.route_continuity and self.regret_repair):
            raise ValueError("RH_REGRET requires persistent routes and regret repair")


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
    diagnostics: dict = field(default_factory=dict)

    def save(self, path):
        save_json(path, self)

    def logical_dict(self):
        result = asdict(self)
        result["searches"] = [{k: v for k, v in s.items() if k not in
                              {"elapsed", "deadline_exceeded", "deadline_overrun_seconds"}} for s in result["searches"]]
        result["metrics"] = {k: v for k, v in result["metrics"].items()
                             if "planning_time" not in k and "overrun" not in k and k != "repair_seconds"}
        result["effective_config"].pop("parallel_agents", None)
        result["effective_config"].pop("workers", None)
        return result


def _plan_job(agent, state, observation, seed, algorithm):
    if algorithm == "GREEDY":
        return greedy_plan(state, observation, agent.controller.config)
    return agent.plan(state, observation, seed)


def unused_symmetry_key(state, observation, config):
    if state.departed or state.finished or state.location.kind != "d" or state.current_committed_action is not None:
        return None
    return replace(state, id=0), observation, config


def rebind_plan(result, vehicle_id):
    def rebind(p):
        end = replace(p.predicted_end_state, id=vehicle_id) if p.predicted_end_state else None
        return replace(p, vehicle_id=vehicle_id, predicted_end_state=end)
    return PlanningResult(tuple(rebind(p) for p in result.proposals), rebind(result.fallback),
                          replace(result.statistics, iterations=0, nodes_expanded=0, elapsed=0),
                          tuple(rebind(p) for p in result.evaluated_proposals))


def idle_proposal(vehicle, observation, config):
    # With a fixed fleet, no known work is not evidence that a route should end.
    # Sleep until the latest safe escape, interruptibly on observable events.
    problem = MPCPlanningProblem(observation, vehicle, replace(config, max_idle_wait=0))
    return problem.proposal((problem.fallback(problem.initial),))


class EventDrivenSimulator:
    def __init__(self, instance: Instance, scenario: DynamicScenario,
                 config: SimulationConfig = SimulationConfig()):
        self.instance, self.scenario, self.config = instance, scenario, config
        if config.algorithm == "MPC_MCTS_H1":
            self.config = replace(config, mpc=replace(config.mpc, prediction_horizon=1))
        self.state = initial_global_state(instance, scenario)
        self.agents = {k: EVAgent(k, self.config.mpc) for k in self.state.vehicles}

    def run(self):
        from .repair import compact_unused_routes, regret_repair, route_proposal
        from .diagnostics import ServiceDiagnostics
        state, instance, config = self.state, self.instance, self.config
        events, steps, decisions, searches, timings = [], [], [], [], []
        tails, coverages, local_times = {}, [], []
        epochs = replans = conflicts = resolved = waits = simulations = expanded = reused = 0
        new_activations = inserted_requests = compacted_vehicles = 0
        repair_seconds = 0.
        diagnostic = ServiceDiagnostics(instance, self.scenario) if config.diagnostics else None
        pool = ProcessPoolExecutor(max_workers=config.workers) if config.parallel_agents else None
        try:
            for _ in range(config.max_events):
                revealed = state.reveal()
                events.extend(SimulationEvent(state.time, "release", customer_id=c) for c in revealed)
                for k in sorted(k for k, s in state.busy.items() if s.after.time <= state.time):
                    step = state.busy.pop(k)
                    state.vehicles[k] = step.after
                    steps.append(step)
                    if step.served:
                        assert state.committed_customers.pop(step.served) == k
                        assert step.served not in state.served_customers
                        state.served_customers.add(step.served)
                    events.append(SimulationEvent(state.time, "complete", k, step.served, step.action))
                state.check_partition(instance)
                ready = [k for k, v in sorted(state.vehicles.items()) if k not in state.busy and not v.finished]
                for k in ready:
                    vehicle = state.vehicles[k]
                    if vehicle.time < state.time:
                        step = transition(vehicle, Action("wait", wait_duration=state.time-vehicle.time),
                                          Observation(vehicle.time, instance.infrastructure, ()))
                        state.vehicles[k] = step.after
                        steps.append(step)
                if not ready and not state.busy:
                    break
                if ready or revealed:
                    observation = get_agent_observation(state, instance)
                    started = perf_counter()
                    origins = {k: state.busy[k].after if k in state.busy else v
                               for k, v in state.vehicles.items()
                               if not (state.busy[k].after if k in state.busy else v).finished}
                    if config.route_continuity:
                        assert_unique_routes(tails)
                    frozen = {k: a for k, a in tails.items() if k not in ready and a}
                    for k, actions in frozen.items():
                        if route_proposal(origins[k], actions, observation, config.mpc) is None:
                            raise RuntimeError("Busy route became infeasible")
                    background = reserved_customers(frozen)
                    jobs = [(self.agents[k], state.vehicles[k], route_observation(observation, frozen, k),
                             agent_seed(config.experiment_seed, self.scenario.scenario_seed, epochs, k),
                             config.algorithm) for k in ready]
                    results, cache = [], {}
                    for job in jobs:
                        agent, vehicle, obs, seed, algorithm = job
                        if algorithm == "RH_REGRET":
                            result = PlanningResult((), idle_proposal(vehicle, obs, config.mpc))
                        else:
                            key = unused_symmetry_key(vehicle, obs, config.mpc) if config.symmetry_reuse else None
                            if key is not None and key in cache:
                                result = rebind_plan(cache[key], vehicle.id)
                                reused += 1
                            else:
                                result = pool.submit(_plan_job, *job).result() if pool else _plan_job(*job)
                                if key is not None:
                                    cache[key] = result
                        results.append(result)
                    plans = {k: with_soft_incumbent(r, state.vehicles[k], job[2], config.mpc,
                                                    tails.get(k, ()) if config.route_continuity else ())
                             for k, r, job in zip(ready, results, jobs)}
                    candidate_coverage = background | set().union(*(set(p.unique_predicted_customer_set)
                                         for r in plans.values() for p in r.candidates))
                    firsts = [p.proposals[0].first.destination for p in plans.values()
                              if p.proposals and p.proposals[0].first.kind == "serve"]
                    duplicates = len(firsts)-len(set(firsts))
                    conflicts += duplicates
                    if config.algorithm in {"GREEDY", "RH_REGRET", "INDEPENDENT_MPC_MCTS"}:
                        selected, count = independent_selection(plans, exclusive_routes=True)
                        resolved += count
                    else:
                        selected = coordinate({k: r.candidates for k, r in plans.items()},
                                              frozenset(state.committed_customers),
                                              available=frozenset(c.id for c in observation.customers),
                                              background_intents=background, exclusive_routes=True)
                        resolved += duplicates
                    routes = dict(frozen)
                    routes.update({k: service_prefix(p.actions) for k, p in selected.items()})
                    coordinated_coverage = reserved_customers(routes)
                    vehicles_before_repair = sum(origins[k].departed or bool(routes.get(k)) for k in origins)
                    distance_before_repair = sum(p.total_predicted_distance for k, a in routes.items() if a
                                                 for p in (route_proposal(origins[k], a, observation, config.mpc),)
                                                 if p is not None)
                    insertions = []
                    compactions = []
                    if config.regret_repair:
                        repair_start = perf_counter()
                        eligible = origins if config.route_continuity else {k: origins[k] for k in ready}
                        routes, insertions = regret_repair(eligible, routes, observation, config.mpc)
                        routes, compactions = compact_unused_routes(eligible, routes, observation, config.mpc)
                        repair_seconds += perf_counter()-repair_start
                        inserted_requests += len(insertions)
                        compacted_vehicles += len(compactions)
                    # One final reconciliation; never cycle repair and coordination.
                    assert_unique_routes(routes)
                    validated = {k: route_proposal(origins[k], a, observation, config.mpc)
                                 for k, a in routes.items() if a}
                    if any(p is None for p in validated.values()):
                        raise RuntimeError("Repair failed final route reconciliation")
                    final_coverage = reserved_customers(routes)
                    distance_after_repair = sum(p.total_predicted_distance for p in validated.values())
                    vehicles_after_compaction = sum(origins[k].departed or bool(routes.get(k)) for k in origins)
                    selected = {k: validated.get(k) or idle_proposal(state.vehicles[k], observation, config.mpc)
                                for k in ready}
                    tails = {k: a for k, a in routes.items() if k not in ready and a} if config.route_continuity else {}
                    timings.append(perf_counter()-started)
                    measured = list(zip(ready, results))
                    if diagnostic:
                        diagnostic.observe(state, observation, plans, selected, measured, 0, config)
                    coverage = set().union(*(set(p.unique_predicted_customer_set) for p in selected.values()))
                    coverages.append(len(coverage))
                    new_activations += sum(p.new_activation for p in selected.values())
                    replans += len(results) if config.algorithm != "RH_REGRET" else 0
                    background = reserved_customers(tails)
                    candidate_intents = sorted(set().union(*(set(p.unique_predicted_customer_set)
                                               for r in plans.values() for p in r.candidates)))
                    decision = dict(epoch=epochs, time=state.time, available=[c.id for c in observation.customers],
                                    committed_before=dict(observation.committed_customers),
                                    candidate_intents=candidate_intents, background_intents=sorted(background),
                                    unique_intention_coverage=sorted(coverage), route_insertions=insertions,
                                    route_compactions=compactions,
                                    route_owners_after_repair={a.destination: k for k, actions in routes.items()
                                                               for a in actions if a.kind == "serve"},
                                    customers_available=len(observation.customers),
                                    coverage_before_coordination=len(candidate_coverage),
                                    coverage_after_coordination=len(coordinated_coverage),
                                    uncovered_before_repair=len(set(c.id for c in observation.customers) - coordinated_coverage),
                                    repair_insertions=len(insertions), coverage_after_repair=len(final_coverage),
                                    vehicles_before_repair=vehicles_before_repair,
                                    vehicles_after_compaction=vehicles_after_compaction,
                                    distance_before_repair=distance_before_repair,
                                    distance_after_repair=distance_after_repair,
                                    selected_firsts=[p.first.destination for p in selected.values() if p.first.kind == "serve"],
                                    plans={str(k): asdict(p) for k, p in selected.items()} if config.trace_level != "none" else {})
                    if config.trace_level == "full":
                        decision["candidates"] = {str(k): [asdict(p) for p in r.candidates] for k, r in plans.items()}
                    decisions.append(decision)
                    for k, r in measured:
                        simulations += r.statistics.iterations
                        expanded += r.statistics.nodes_expanded
                        if config.algorithm not in {"GREEDY", "RH_REGRET"}:
                            local_times.append(r.statistics.elapsed)
                        if config.trace_level != "none":
                            details = asdict(r.statistics)
                            if config.trace_level == "summary":
                                details.pop("root_actions", None)
                            searches.append(dict(epoch=epochs, vehicle_id=k, **details))
                    for k, p in selected.items():
                        step = transition(state.vehicles[k], p.first, observation)
                        if config.route_continuity:
                            tails[k] = service_tail(p)
                        events.append(SimulationEvent(state.time, "dispatch", k, step.served, p.first))
                        if p.first.kind == "wait":
                            state.idle_until[k] = step.after.time
                            waits += 1
                        else:
                            state.idle_until.pop(k, None)
                            state.busy[k] = step
                            state.vehicles[k] = replace(state.vehicles[k], status="busy", current_committed_action=p.first)
                            if step.served:
                                assert step.served in state.available_customers
                                state.available_customers.pop(step.served)
                                state.committed_customers[step.served] = k
                    assert_unique_routes(tails)
                    epochs += 1
                    state.check_partition(instance)
                future = [t for _, t in state.hidden_customers.values() if t > state.time]
                future.extend(s.after.time for s in state.busy.values())
                future.extend(t for k, t in state.idle_until.items() if not state.vehicles[k].finished)
                if not future:
                    break
                next_time = min(future)
                if next_time < state.time or next_time > instance.infrastructure.depot.due+EPS:
                    raise RuntimeError("Invalid next event time")
                state.time = next_time
            else:
                raise RuntimeError("Simulation event guard exceeded")
        finally:
            if pool:
                pool.shutdown(wait=True, cancel_futures=True)
        events.append(SimulationEvent(state.time, "end"))
        served, total = len(state.served_customers), len(instance.customers)
        distance = sum(s.distance for s in steps)
        returned = all(v.finished and v.location.kind == "d" for v in state.vehicles.values())
        metrics = dict(feasible=served == total and returned, customers_served=served,
                       complete_service=served == total, customers_unserved=total-served,
                       service_ratio=served/total if total else 1., total_distance=distance,
                       distance_per_served_customer=distance/served if served else None,
                       vehicles_activated=sum(v.departed for v in state.vehicles.values()),
                       total_charging_visits=sum(s.action.kind == "charge" for s in steps),
                       total_energy_charged=sum(s.energy_charged for s in steps),
                       total_charging_time=sum(s.charging_time for s in steps),
                       total_waiting_time=sum(s.waiting_time for s in steps), final_return_feasibility=returned,
                       time_window_violations=sum(s.action.kind == "serve" and s.service_start > s.after.location.due+EPS for s in steps),
                       battery_violations=sum(s.after.battery < -EPS or s.after.battery > instance.infrastructure.parameters.battery+EPS for s in steps),
                       capacity_violations=sum(s.after.load < -EPS for s in steps), decision_epochs=epochs,
                       duplicate_customer_proposal_conflicts=conflicts, conflicts_resolved=resolved,
                       wait_selected=waits, agent_replans=replans,
                       mean_unique_intention_coverage=float(np.mean(coverages)) if coverages else 0.,
                       vehicle_activations_caused_by_coordinator=new_activations if config.algorithm in {"COORDINATED_MPC_MCTS", "MPC_MCTS_H1"} else 0,
                       duplicate_service_violations=0, hidden_information_violations=0,
                       symmetry_reused_replans=reused, mcts_iterations=simulations, nodes_expanded=expanded,
                       route_insertions=inserted_requests, route_compactions=compacted_vehicles,
                       repair_seconds=repair_seconds,
                       deadline_overrun_rate=float(np.mean(np.array(local_times) > config.mpc.time_limit))
                       if local_times and config.mpc.budget_mode == "wall_clock" else None)
        for name, fn in [("mean", np.mean), ("median", np.median), ("p95", lambda x: np.percentile(x, 95)), ("maximum", np.max), ("total", np.sum)]:
            metrics[f"{name}_planning_time"] = float(fn(timings)) if timings else 0.
        import re
        metadata = dict(instance=instance.name, instance_sha256=instance.sha256,
                        instance_family=re.match(r"([a-z]+[12])", instance.name).group(1).upper(),
                        number_of_customers=total, number_of_stations=len(instance.infrastructure.stations),
                        K=self.scenario.fleet_size, K_ref=self.scenario.fleet_size, K_max=self.scenario.fleet_size,
                        fleet_mode=config.fleet_mode, DoD_target=self.scenario.target_DoD,
                        DoD_realized=self.scenario.realized_DoD, scenario_seed=self.scenario.scenario_seed,
                        scenario_identifier=self.scenario.identifier, algorithm_seed=config.experiment_seed,
                        algorithm=config.algorithm, reference_schedule_identifier=self.scenario.reference_schedule_identifier)
        return ExperimentResult(metadata, asdict(config), metrics, events, steps, decisions, searches,
                                sorted(c.id for c in instance.customers if c.id not in state.served_customers),
                                diagnostic.finish(state) if diagnostic else {})

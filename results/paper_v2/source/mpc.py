"""Explicit event-triggered MPC formulation, independent of its numerical optimizer."""

from dataclasses import dataclass, field
from math import isfinite

from .instance import distance, energy, travel_time
from .model import (EPS, Action, InfeasibleAction, Observation, Transition, VehicleState,
                    escape, escape_action, transition)
from .reference import full_charge_connection
from . import performance as perf


@dataclass(frozen=True)
class MPCConfig:
    prediction_horizon: int = 5
    control_horizon: int = 1
    top_l: int = 3
    candidate_limit: int = 12
    iterations: int = 32
    station_candidate_limit: int = 4
    charge_target_limit: int = 5
    action_space_reduction: bool = True
    cache_transitions: bool = True
    require_root_coverage: bool = False
    max_idle_wait: float = 0.0
    uct_c: float = 1.4
    budget_mode: str = "iterations"
    time_limit: float = 0.5
    charging_mode: str = "partial"
    charge_fractions: tuple[float, ...] = (0.5, 0.75, 1.0)

    def __post_init__(self):
        if self.control_horizon != 1:
            raise ValueError("Control horizon must equal one")
        for value in (self.prediction_horizon, self.top_l, self.candidate_limit, self.iterations,
                      self.station_candidate_limit, self.charge_target_limit):
            if type(value) is not int or value < 1:
                raise ValueError("MPC integer budgets must be positive")
        if self.budget_mode not in {"iterations", "wall_clock"} or self.charging_mode not in {"full", "partial"}:
            raise ValueError("Unknown computation budget or charging mode")
        if not isfinite(self.uct_c) or self.uct_c < 0 or not isfinite(self.time_limit) or self.time_limit <= 0:
            raise ValueError("Invalid UCT coefficient or wall-clock budget")
        if not self.charge_fractions or any(not isfinite(v) or not 0 < v <= 1 for v in self.charge_fractions):
            raise ValueError("Charge fractions must lie in (0, 1]")
        if not isfinite(self.max_idle_wait) or self.max_idle_wait < 0:
            raise ValueError("Idle wait bound must be finite and nonnegative")


@dataclass(frozen=True)
class MPCState:
    vehicle: VehicleState
    remaining: frozenset[str]
    service_depth: int = 0
    station_visits_since_service: frozenset[str] = frozenset()
    stopped: bool = False


@dataclass(frozen=True)
class MPCProposal:
    actions: tuple[Action, ...]
    cost: float
    visits: int = 0
    vehicle_id: int = 0
    predicted_end_state: VehicleState | None = None
    predicted_distance: float = 0.0
    predicted_charging_actions: int = 0
    predicted_customer_sequence: tuple[str, ...] = ()
    charging_time: float = 0.0
    waiting_time: float = 0.0
    completion_time: float = 0.0
    terminal_return_distance: float = 0.0
    new_activation: bool = False
    mcts_value_estimate: float | None = None
    unique_predicted_customer_set: tuple[str, ...] = field(init=False)
    predicted_service_count: int = field(init=False)
    total_predicted_distance: float = field(init=False)
    first_action: Action = field(init=False)
    root_visits: int = field(init=False)

    def __post_init__(self):
        if not self.actions:
            raise ValueError("Proposal must contain a first action")
        sequence = tuple(a.destination for a in self.actions if a.kind == "serve")
        if self.predicted_customer_sequence and self.predicted_customer_sequence != sequence:
            raise ValueError("Proposal sequence differs from its actions")
        if len(sequence) != len(set(sequence)):
            raise ValueError("Duplicate predicted service")
        object.__setattr__(self, "predicted_customer_sequence", sequence)
        object.__setattr__(self, "unique_predicted_customer_set", tuple(sorted(set(sequence))))
        object.__setattr__(self, "predicted_service_count", len(sequence))
        object.__setattr__(self, "total_predicted_distance", self.cost)
        object.__setattr__(self, "first_action", self.actions[0])
        object.__setattr__(self, "root_visits", self.visits)

    @property
    def first(self) -> Action:
        return self.actions[0]

    @property
    def estimated_mpc_cost(self) -> float:
        return self.cost

    @property
    def predicted_tail(self) -> tuple[Action, ...]:
        return self.actions[1:]


@dataclass(frozen=True)
class SearchStatistics:
    iterations: int = 0
    nodes_expanded: int = 0
    elapsed: float = 0.0
    root_actions: tuple[dict, ...] = ()
    root_action_count: int = 0
    root_actions_evaluated: int = 0
    minimum_root_visits: int = 0
    fraction_root_actions_evaluated: float = 1.0


@dataclass(frozen=True)
class PlanningResult:
    proposals: tuple[MPCProposal, ...]
    fallback: MPCProposal
    statistics: SearchStatistics = field(default_factory=SearchStatistics)
    evaluated_proposals: tuple[MPCProposal, ...] = ()

    @property
    def candidates(self) -> tuple[MPCProposal, ...]:
        return self.proposals if any(p.first == self.fallback.first for p in self.proposals) else self.proposals + (self.fallback,)


def action_key(action: Action) -> tuple:
    return action.kind, action.destination, action.target_battery, action.wait_duration


def proposal_key(proposal: MPCProposal) -> tuple:
    return (-proposal.predicted_service_count, proposal.total_predicted_distance, proposal.charging_time, proposal.waiting_time,
            proposal.completion_time, tuple(action_key(a) for a in proposal.actions))


@dataclass(frozen=True)
class MPCPlanningProblem:
    observation: Observation
    current_state: VehicleState
    config: MPCConfig
    _transitions: dict = field(default_factory=dict, init=False, compare=False, repr=False, hash=False)
    _returns: dict = field(default_factory=dict, init=False, compare=False, repr=False, hash=False)

    @property
    def initial(self) -> MPCState:
        return MPCState(self.current_state, frozenset(c.id for c in self.observation.customers))

    def predict(self, state: MPCState, action: Action) -> tuple[MPCState, Transition]:
        key = (state, action)
        if self.config.cache_transitions and key in self._transitions:
            perf.count("transition_cache_hits")
            result = self._transitions[key]
            if isinstance(result[0], str):
                raise InfeasibleAction(*result)
            return result
        try:
            result = self._predict(state, action)
        except InfeasibleAction as error:
            if self.config.cache_transitions:
                self._transitions[key] = (str(error), error.reason)
            raise
        if self.config.cache_transitions:
            self._transitions[key] = result
        return result

    def _predict(self, state: MPCState, action: Action) -> tuple[MPCState, Transition]:
        if action.kind == "serve" and action.destination not in state.remaining:
            raise InfeasibleAction("Customer unavailable or already served in prediction")
        if action.kind == "charge" and self.config.charging_mode == "full":
            if abs(action.target_battery - self.observation.infrastructure.parameters.battery) > EPS:
                raise InfeasibleAction("Full charging mode requires target Q")
        step = transition(state.vehicle, action, self.observation)
        remaining = state.remaining - {step.served} if step.served else state.remaining
        visited = frozenset() if step.served else state.station_visits_since_service
        if action.kind == "charge":
            if action.destination in visited:
                raise InfeasibleAction("Repeated station without intervening service")
            visited = visited | {action.destination}
        new = MPCState(step.after, remaining, state.service_depth + int(step.served is not None),
                       visited, action.kind in {"wait", "return"})
        if self.config.charging_mode == "full" and self.return_connection(step.after) is None:
            raise InfeasibleAction("Full-recharge policy cannot return safely")
        return new, step

    def return_connection(self, state: VehicleState) -> tuple[Transition, ...] | None:
        if state.finished:
            return ()
        if state not in self._returns:
            self._returns[state] = full_charge_connection(state, Action("return", self.observation.infrastructure.depot.id), self.observation)
        return self._returns[state]

    def stage_cost(self, step: Transition) -> float:
        return step.distance

    def reward(self, proposal: MPCProposal) -> float:
        """One service dominates the entire [0, 0.5] distance contribution."""
        infra = self.observation.infrastructure
        bound = infra.parameters.speed * max(0.0, infra.depot.due - self.current_state.time)
        if proposal.total_predicted_distance < 0 or proposal.total_predicted_distance > bound + 1e-6:
            raise ValueError("Feasible route exceeds remaining-time distance bound")
        normalized = min(1.0, proposal.total_predicted_distance / bound) if bound > 0 else 0.0
        return proposal.predicted_service_count - 0.5 * normalized

    def terminal_cost(self, state: MPCState) -> float:
        if self.config.charging_mode == "full":
            route = self.return_connection(state.vehicle)
            return sum(s.distance for s in route) if route is not None else float("inf")
        safe = escape(state.vehicle, self.observation.infrastructure)
        return safe.distance if safe and safe.completion <= self.observation.infrastructure.depot.due + EPS else float("inf")

    def fallback(self, state: MPCState) -> Action:
        vehicle, infra = state.vehicle, self.observation.infrastructure
        safe = escape(vehicle, infra)
        if safe is None:
            raise InfeasibleAction("Stranded measured state")
        if self.config.charging_mode == "full":
            route = self.return_connection(vehicle)
            if route is None:
                raise InfeasibleAction("No full-charge return")
            completion = route[-1].after.time if route else vehicle.time
            returning = route[0].action if route else Action("return", infra.depot.id)
        else:
            completion, returning = safe.completion, escape_action(vehicle, infra)
        slack = infra.depot.due - completion
        if self.config.max_idle_wait and vehicle.departed and not self.customer_pool(state, require_energy=False):
            return returning
        if slack > EPS:
            if self.config.max_idle_wait:
                slack = min(slack, self.config.max_idle_wait)
            return Action("wait", wait_duration=slack)
        return returning

    def done(self, state: MPCState) -> bool:
        return state.stopped or state.vehicle.finished or state.service_depth >= self.config.prediction_horizon

    def customer_rank(self, state: MPCState, action: Action) -> tuple:
        customer = self.observation.customer_by_id[action.destination]
        _, step = self.predict(state, action)
        slack = customer.due - step.service_start
        return (slack, step.distance, step.waiting_time, customer.id)

    def actions(self, state: MPCState) -> tuple[Action, ...]:
        if not self.config.action_space_reduction:
            return self._exhaustive_actions(state)
        if self.done(state):
            return ()
        measured = perf.stamp()
        pool = self.customer_pool(state)
        perf.elapsed("customer_ranking", measured)
        measured = perf.stamp()
        feasible = []
        for customer in pool:
            perf.count("customer_actions_considered")
            action = Action("serve", customer.id)
            try:
                self.predict(state, action)
                feasible.append(action)
            except InfeasibleAction:
                pass
        perf.elapsed("customer_feasibility", measured)
        proposed = feasible[:self.config.candidate_limit]
        proposed.append(self.fallback(state))
        infra, vehicle = self.observation.infrastructure, state.vehicle
        returning = None
        if vehicle.departed:
            if self.config.charging_mode == "full":
                route = self.return_connection(vehicle)
                returning = route[0].action if route else None
            else:
                returning = escape_action(vehicle, infra)
        measured = perf.stamp()
        proposed.extend(self.charge_actions(state, returning))
        perf.elapsed("charging_generation", measured)
        if returning is not None:
            proposed.append(returning)
        valid = []
        for action in dict.fromkeys(proposed):
            try:
                self.predict(state, action)
                valid.append(action)
            except InfeasibleAction:
                pass
        perf.count("charge_actions_retained", sum(a.kind == "charge" for a in valid))
        perf.branching(valid)
        return tuple(valid)

    def customer_pool(self, state: MPCState, require_energy=True):
        """Cheap urgency/proximity union, at most twice the service candidate limit."""
        vehicle, p = state.vehicle, self.observation.infrastructure.parameters
        candidates = []
        for customer in self.observation.customers:
            if customer.id not in state.remaining or customer.demand > vehicle.load + EPS:
                continue
            leg = distance(vehicle.location, customer)
            start = max(vehicle.time + leg / p.speed, customer.ready)
            if start > customer.due + EPS:
                continue
            if require_energy and leg * p.consumption > vehicle.battery + EPS:
                continue
            candidates.append((customer.due-start, leg, customer.id, customer))
        limit = self.config.candidate_limit
        urgent = sorted(candidates)[:limit]
        nearest = sorted(candidates, key=lambda row: (row[1], row[2]))[:limit]
        result = {}
        for a, b in zip(urgent, nearest):
            result.setdefault(a[2], a[3])
            result.setdefault(b[2], b[3])
        return tuple(result.values())

    def charge_actions(self, state, returning=None):
        infra, vehicle = self.observation.infrastructure, state.vehicle
        p = infra.parameters
        customers = self.customer_pool(state, require_energy=False)
        safe = (infra.depot,) + infra.stations
        reserves = {c.id: min(energy(c, n, p) for n in safe) for c in customers}
        stations = [s for s in infra.stations if s.id != vehicle.location.id
                    and s.id not in state.station_visits_since_service
                    and energy(vehicle.location, s, p) <= vehicle.battery + EPS]
        selected = {}
        mandatory = returning if returning and returning.kind == "charge" else None
        if mandatory:
            selected[mandatory.destination] = infra.node_by_id[mandatory.destination]
        # Safe return first, then nearest and low-detour stations toward urgent work.
        nearest = sorted(stations, key=lambda s: (distance(vehicle.location, s), s.id))
        urgent = sorted(customers, key=lambda c: (c.due-max(c.ready, vehicle.time + travel_time(vehicle.location, c, p)), c.id))[:3]
        def detour(s):
            return min((distance(vehicle.location, s) + distance(s, c) - distance(vehicle.location, c)
                        for c in urgent if energy(s, c, p) + reserves[c.id] <= p.battery + EPS), default=float("inf"))
        toward = sorted(stations, key=lambda s: (detour(s), distance(vehicle.location, s), s.id))
        for a, b in zip(nearest, toward):
            for station in (a, b):
                if len(selected) < self.config.station_candidate_limit:
                    selected.setdefault(station.id, station)
        actions = []
        for station in selected.values():
            arrival = vehicle.battery - energy(vehicle.location, station, p)
            priorities = []
            if mandatory and mandatory.destination == station.id:
                priorities.append(mandatory.target_battery)
            if self.config.charging_mode == "partial":
                # Minimum safe-return energy, not a rounded SOC bin.
                tail = escape(VehicleState(vehicle.id, station, 0, p.battery, vehicle.load), infra)
                if tail is not None:
                    priorities.append(min(p.battery, tail.distance * p.consumption))
                needs = [energy(station, c, p) + reserves[c.id] for c in customers]
                viable = [n for n in needs if arrival + EPS < n <= p.battery + EPS]
                if viable:
                    priorities.append(min(viable))
                priorities.extend(p.battery * f for f in self.config.charge_fractions)
                priorities.extend(viable)
            priorities.append(p.battery)
            targets = []
            for target in priorities:
                if not arrival + EPS < target <= p.battery + EPS:
                    continue
                if all(abs(target-t) > EPS for t in targets):
                    targets.append(target)
                if len(targets) == self.config.charge_target_limit:
                    break
            # Different SOC/time tradeoffs are not falsely declared dominated.
            # Zero-increment and EPS-equivalent targets have already been removed.
            actions.extend(Action("charge", station.id, t) for t in sorted(targets))
        perf.count("charge_actions_generated", len(actions))
        return actions

    def _exhaustive_actions(self, state: MPCState) -> tuple[Action, ...]:
        """Legacy action set retained only for exact-computation regression tests."""
        if self.done(state):
            return ()
        vehicle, infra = state.vehicle, self.observation.infrastructure
        p = infra.parameters
        customers = [c for c in self.observation.customers if c.id in state.remaining]
        feasible = []
        measured = perf.stamp()
        for customer in customers:
            perf.count("customer_actions_considered")
            action = Action("serve", customer.id)
            try:
                self.predict(state, action)
                feasible.append(action)
            except InfeasibleAction:
                continue
        perf.elapsed("customer_feasibility", measured)
        measured = perf.stamp()
        urgent = sorted(feasible, key=lambda a: self.customer_rank(state, a))
        nearest = sorted(feasible, key=lambda a: (distance(vehicle.location, next(c for c in customers if c.id == a.destination)), a.destination))
        proposed = []
        # Interleave urgency and proximity so nearest-only pruning cannot hide urgent work.
        for pair in zip(urgent, nearest):
            for action in pair:
                if action not in proposed and len(proposed) < self.config.candidate_limit:
                    proposed.append(action)
        perf.elapsed("customer_ranking", measured)
        proposed.append(self.fallback(state))
        if vehicle.departed:
            if self.config.charging_mode == "full":
                route = self.return_connection(vehicle)
                if route:
                    proposed.append(route[0].action)
            else:
                proposed.append(escape_action(vehicle, infra))
        safe_nodes = (infra.depot,) + infra.stations
        measured = perf.stamp()
        for station in infra.stations:
            if station.id in state.station_visits_since_service or station.id == vehicle.location.id:
                continue
            arrival = vehicle.battery - distance(vehicle.location, station) * p.consumption
            if arrival < -EPS:
                continue
            targets = {p.battery}
            if self.config.charging_mode == "partial":
                targets.update(p.battery * f for f in self.config.charge_fractions)
                targets.update(distance(station, node) * p.consumption for node in safe_nodes)
                for customer in customers:
                    if customer.demand <= vehicle.load + EPS:
                        reserve = min(distance(customer, node) for node in safe_nodes)
                        targets.add((distance(station, customer) + reserve) * p.consumption)
            unique = []
            for target in sorted(targets):
                if arrival + EPS < target <= p.battery + EPS and (not unique or target - unique[-1] > EPS):
                    unique.append(target)
            proposed.extend(Action("charge", station.id, target) for target in unique)
            perf.count("charge_actions_generated", len(unique))
        perf.elapsed("charging_generation", measured)
        valid = []
        for action in dict.fromkeys(proposed):
            try:
                self.predict(state, action)
                valid.append(action)
            except InfeasibleAction:
                continue
        perf.count("charge_actions_retained", sum(a.kind == "charge" for a in valid))
        perf.branching(valid)
        return tuple(valid)

    def proposal(self, actions: tuple[Action, ...], visits: int = 0) -> MPCProposal:
        if not actions:
            raise ValueError("Empty proposal")
        state, cost, charged, activation = self.initial, 0.0, 0, False
        for action in actions:
            if self.done(state):
                raise ValueError("Plan extends beyond its horizon")
            state, step = self.predict(state, action)
            if step.before == self.current_state:
                activation = not self.current_state.departed and step.after.departed and action.kind in {"serve", "charge"}
            cost += self.stage_cost(step)
            charged += int(action.kind == "charge")
        return self.proposal_from_state(actions, state, cost, charged, activation, visits)

    def proposal_from_state(self, actions, state, cost, charged=None, activation=None, visits=0):
        vehicle = state.vehicle
        if charged is None:
            charged = sum(a.kind == "charge" for a in actions)
        if activation is None:
            _, first = self.predict(self.initial, actions[0])
            activation = not self.current_state.departed and first.after.departed and actions[0].kind in {"serve", "charge"}
        terminal = self.terminal_cost(state)
        return MPCProposal(actions, cost + terminal, visits, vehicle.id, vehicle, cost,
                           charged, tuple(a.destination for a in actions if a.kind == "serve"),
                           vehicle.charging_time - self.current_state.charging_time,
                           vehicle.waiting_time - self.current_state.waiting_time, vehicle.time,
                           terminal, activation)


class MPCController:
    def __init__(self, config: MPCConfig):
        from .mcts import MCTSOptimizer

        self.config = config
        self.optimizer = MCTSOptimizer()

    def formulate(self, state: VehicleState, observation: Observation) -> MPCPlanningProblem:
        return MPCPlanningProblem(observation, state, self.config)

    def plan(self, state: VehicleState, observation: Observation, seed: int) -> PlanningResult:
        return self.optimizer.solve(self.formulate(state, observation), seed)


FiniteHorizonPlanningProblem = MPCPlanningProblem
MPCProblem = MPCPlanningProblem
CandidatePlan = MPCProposal

"""Explicit event-triggered MPC formulation, independent of its numerical optimizer."""

from dataclasses import dataclass, field
from math import isfinite

from .instance import distance
from .model import (EPS, Action, InfeasibleAction, Observation, Transition, VehicleState,
                    escape, escape_action, transition)
from .reference import full_charge_connection


@dataclass(frozen=True)
class MPCConfig:
    prediction_horizon: int = 5
    control_horizon: int = 1
    top_l: int = 3
    candidate_limit: int = 12
    iterations: int = 250
    uct_c: float = 1.4
    budget_mode: str = "iterations"
    time_limit: float = 0.5
    charging_mode: str = "partial"
    charge_fractions: tuple[float, ...] = (0.5, 0.75, 1.0)

    def __post_init__(self):
        if self.control_horizon != 1:
            raise ValueError("Control horizon must equal one")
        for value in (self.prediction_horizon, self.top_l, self.candidate_limit, self.iterations):
            if type(value) is not int or value < 1:
                raise ValueError("MPC integer budgets must be positive")
        if self.budget_mode not in {"iterations", "wall_clock"} or self.charging_mode not in {"full", "partial"}:
            raise ValueError("Unknown computation budget or charging mode")
        if not isfinite(self.uct_c) or self.uct_c < 0 or not isfinite(self.time_limit) or self.time_limit <= 0:
            raise ValueError("Invalid UCT coefficient or wall-clock budget")
        if not self.charge_fractions or any(not isfinite(v) or not 0 < v <= 1 for v in self.charge_fractions):
            raise ValueError("Charge fractions must lie in (0, 1]")


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


@dataclass(frozen=True)
class PlanningResult:
    proposals: tuple[MPCProposal, ...]
    fallback: MPCProposal
    statistics: SearchStatistics = field(default_factory=SearchStatistics)

    @property
    def candidates(self) -> tuple[MPCProposal, ...]:
        return self.proposals if any(p.first == self.fallback.first for p in self.proposals) else self.proposals + (self.fallback,)


def action_key(action: Action) -> tuple:
    return action.kind, action.destination, action.target_battery, action.wait_duration


def proposal_key(proposal: MPCProposal) -> tuple:
    return (proposal.cost, proposal.charging_time, proposal.waiting_time,
            proposal.completion_time, tuple(action_key(a) for a in proposal.actions))


@dataclass(frozen=True)
class MPCPlanningProblem:
    observation: Observation
    current_state: VehicleState
    config: MPCConfig

    @property
    def initial(self) -> MPCState:
        return MPCState(self.current_state, frozenset(c.id for c in self.observation.customers))

    def predict(self, state: MPCState, action: Action) -> tuple[MPCState, Transition]:
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
        return full_charge_connection(state, Action("return", self.observation.infrastructure.depot.id), self.observation)

    def stage_cost(self, step: Transition) -> float:
        return step.distance

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
        if slack > EPS:
            return Action("wait", wait_duration=slack)
        return returning

    def done(self, state: MPCState) -> bool:
        return state.stopped or state.vehicle.finished or state.service_depth >= self.config.prediction_horizon

    def customer_rank(self, state: MPCState, action: Action) -> tuple:
        customer = next(c for c in self.observation.customers if c.id == action.destination)
        step = transition(state.vehicle, action, self.observation)
        slack = customer.due - step.service_start
        return (slack, step.distance, step.waiting_time, customer.id)

    def actions(self, state: MPCState) -> tuple[Action, ...]:
        if self.done(state):
            return ()
        vehicle, infra = state.vehicle, self.observation.infrastructure
        p = infra.parameters
        customers = [c for c in self.observation.customers if c.id in state.remaining]
        feasible = []
        for customer in customers:
            action = Action("serve", customer.id)
            try:
                self.predict(state, action)
                feasible.append(action)
            except InfeasibleAction:
                continue
        urgent = sorted(feasible, key=lambda a: self.customer_rank(state, a))
        nearest = sorted(feasible, key=lambda a: (distance(vehicle.location, next(c for c in customers if c.id == a.destination)), a.destination))
        proposed = []
        # Interleave urgency and proximity so nearest-only pruning cannot hide urgent work.
        for pair in zip(urgent, nearest):
            for action in pair:
                if action not in proposed and len(proposed) < self.config.candidate_limit:
                    proposed.append(action)
        proposed.append(self.fallback(state))
        if vehicle.departed:
            if self.config.charging_mode == "full":
                route = self.return_connection(vehicle)
                if route:
                    proposed.append(route[0].action)
            else:
                proposed.append(escape_action(vehicle, infra))
        safe_nodes = (infra.depot,) + infra.stations
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
        valid = []
        for action in dict.fromkeys(proposed):
            try:
                self.predict(state, action)
                valid.append(action)
            except InfeasibleAction:
                continue
        return tuple(valid)

    def proposal(self, actions: tuple[Action, ...], visits: int = 0) -> MPCProposal:
        if not actions:
            raise ValueError("Empty proposal")
        state, cost, charged = self.initial, 0.0, 0
        for action in actions:
            if self.done(state):
                raise ValueError("Plan extends beyond its horizon")
            state, step = self.predict(state, action)
            cost += self.stage_cost(step)
            charged += int(action.kind == "charge")
        vehicle = state.vehicle
        return MPCProposal(actions, cost + self.terminal_cost(state), visits, vehicle.id, vehicle, cost,
                           charged, tuple(a.destination for a in actions if a.kind == "serve"),
                           vehicle.charging_time - self.current_state.charging_time,
                           vehicle.waiting_time - self.current_state.waiting_time, vehicle.time)


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

"""Shared deterministic plant model. Planning receives only Observation objects."""

from dataclasses import dataclass, replace
from functools import lru_cache, cached_property
from enum import StrEnum
import heapq
from math import inf, isfinite

from .instance import Infrastructure, Location, FrozenMap, distance, travel_time, energy

EPS = 1e-8


@dataclass(frozen=True)
class VehicleState:
    id: int
    location: Location
    time: float
    battery: float
    load: float
    departed: bool = False
    finished: bool = False
    status: str = "idle"
    current_committed_action: "Action | None" = None
    route_history: tuple[str, ...] = ()
    served_customers: tuple[str, ...] = ()
    distance_travelled: float = 0.0
    charging_time: float = 0.0
    waiting_time: float = 0.0


@dataclass(frozen=True)
class Action:
    kind: str
    destination: str = ""
    target_battery: float = 0.0
    wait_duration: float = 0.0


@dataclass(frozen=True)
class Observation:
    time: float
    infrastructure: Infrastructure
    customers: tuple[Location, ...]
    committed_customers: tuple[tuple[str, int], ...] = ()

    @cached_property
    def customer_by_id(self):
        return FrozenMap((c.id, c) for c in self.customers)

    @cached_property
    def committed_ids(self):
        return frozenset(c for c, _ in self.committed_customers)


@dataclass(frozen=True)
class Transition:
    before: VehicleState
    after: VehicleState
    action: Action
    distance: float
    energy_charged: float
    arrival: float
    service_start: float
    served: str | None

    @property
    def feasible(self) -> bool:
        return True

    @property
    def next_state(self) -> VehicleState:
        return self.after

    @property
    def travel_time(self) -> float:
        return self.arrival - self.before.time

    @property
    def waiting_time(self) -> float:
        return self.after.waiting_time - self.before.waiting_time

    @property
    def energy_consumed(self) -> float:
        return self.before.battery + self.energy_charged - self.after.battery

    @property
    def charging_time(self) -> float:
        return self.after.charging_time - self.before.charging_time

    @property
    def service_finish(self) -> float:
        return self.after.time

    @property
    def infeasibility_reason(self) -> None:
        return None


@dataclass(frozen=True)
class Escape:
    distance: float
    completion: float
    path: tuple[Location, ...]


class InfeasibilityReason(StrEnum):
    BATTERY = "BATTERY"
    CAPACITY = "CAPACITY"
    TIME_WINDOW = "TIME_WINDOW"
    DEPOT_HORIZON = "DEPOT_HORIZON"
    UNREACHABLE_SAFE_CONTINUATION = "UNREACHABLE_SAFE_CONTINUATION"
    INVALID_ACTION = "INVALID_ACTION"


class InfeasibleAction(ValueError):
    def __init__(self, message: str, reason: InfeasibilityReason = InfeasibilityReason.INVALID_ACTION):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class RejectedTransition:
    infeasibility_reason: InfeasibilityReason
    detail: str
    feasible: bool = False
    next_state: None = None


@lru_cache(maxsize=128)
def station_paths(infra: Infrastructure) -> tuple[tuple[float, tuple[Location, ...]], ...]:
    """Shortest station-network paths to depot, with each leg battery-feasible."""
    nodes = (infra.depot,) + infra.stations
    p = infra.parameters
    distances = [inf] * len(nodes)
    paths: list[tuple[Location, ...]] = [()] * len(nodes)
    distances[0] = 0.0
    queue = [(0.0, 0)]
    while queue:
        cost, i = heapq.heappop(queue)
        if cost != distances[i]:
            continue
        for j in range(1, len(nodes)):
            leg = distance(nodes[i], nodes[j])
            if leg * p.consumption > p.battery + EPS:
                continue
            alternative = cost + leg
            if alternative < distances[j]:
                distances[j] = alternative
                paths[j] = (nodes[i],) + paths[i]
                heapq.heappush(queue, (alternative, j))
    return tuple(zip(distances[1:], paths[1:]))


@lru_cache(maxsize=32768)
def _escape_geometry(location: Location, battery: float, infra: Infrastructure):
    """Return geometry depends on exact location/SOC, not vehicle history or time."""
    p = infra.parameters
    direct = distance(location, infra.depot)
    best_distance = inf
    best_path: tuple[Location, ...] = ()
    if direct * p.consumption <= battery + EPS:
        best_distance, best_path = direct, (infra.depot,)
    for station, (tail, path) in zip(infra.stations, station_paths(infra)):
        leg = distance(location, station)
        if leg * p.consumption <= battery + EPS and leg + tail < best_distance:
            best_distance, best_path = leg + tail, (station,) + path
    if not isfinite(best_distance):
        return None
    return best_distance, best_path


def escape(state: VehicleState, infra: Infrastructure) -> Escape | None:
    """Exact earliest return for common hours and uniform linear charging.

    No SOC rounding: completion time is evaluated for the actual state time.
    The shortest reachable station path minimizes both distance and return time.
    """
    route = _escape_geometry(state.location, state.battery, infra)
    if route is None:
        return None
    best_distance, best_path = route
    p = infra.parameters
    completion = state.time + best_distance / p.speed + p.inverse_charge_rate * max(
        0.0, best_distance * p.consumption - state.battery)
    return Escape(best_distance, completion, best_path)


def transition(state: VehicleState, action: Action, observation: Observation,
               require_return: bool = True) -> Transition:
    infra = observation.infrastructure
    p = infra.parameters
    if state.finished or state.time < observation.time - EPS:
        raise InfeasibleAction("Vehicle is finished or state precedes observation")
    if (not all(isfinite(v) for v in (state.time, state.battery, state.load,
                                    action.target_battery, action.wait_duration))
            or not -EPS <= state.battery <= p.battery + EPS
            or not -EPS <= state.load <= p.capacity + EPS):
        raise InfeasibleAction("Invalid physical state or action")
    charged, traveled = 0.0, 0.0
    served = None
    if action.kind == "wait":
        if action.wait_duration <= 0 or state.time + action.wait_duration == state.time:
            raise InfeasibleAction("Wait must advance time")
        arrival = start = state.time
        after = replace(state, time=state.time + action.wait_duration,
                        waiting_time=state.waiting_time + action.wait_duration,
                        status="idle", current_committed_action=None)
    else:
        if action.kind == "serve":
            destination = observation.customer_by_id.get(action.destination)
        elif action.kind == "charge":
            destination = infra.node_by_id.get(action.destination)
            if destination is not None and destination.kind != "f":
                destination = None
        elif action.kind == "return":
            destination = infra.depot if action.destination == infra.depot.id else None
        else:
            raise InfeasibleAction("Unknown action kind")
        if destination is None:
            raise InfeasibleAction("Destination is unavailable in this observation")
        if action.kind == "serve" and (destination.id in state.served_customers or
                destination.id in observation.committed_ids):
            raise InfeasibleAction("Customer is already served or committed")
        traveled = distance(state.location, destination)
        battery = state.battery - energy(state.location, destination, p)
        if battery < -EPS:
            raise InfeasibleAction("Insufficient battery", InfeasibilityReason.BATTERY)
        battery = max(0.0, battery)
        arrival = state.time + travel_time(state.location, destination, p)
        start = max(arrival, destination.ready)
        if start > destination.due + EPS:
            reason = InfeasibilityReason.DEPOT_HORIZON if destination.kind == "d" else InfeasibilityReason.TIME_WINDOW
            raise InfeasibleAction("Hard time window violated", reason)
        end = start
        load = state.load
        if action.kind == "serve":
            if destination.demand > load + EPS:
                raise InfeasibleAction("Insufficient payload", InfeasibilityReason.CAPACITY)
            end += destination.service
            load = max(0.0, load - destination.demand)
            served = destination.id
        elif action.kind == "charge":
            if not battery - EPS <= action.target_battery <= p.battery + EPS:
                raise InfeasibleAction("Charge target must be between arrival battery and capacity")
            charged = max(0.0, min(p.battery, action.target_battery) - battery)
            if charged <= EPS:
                raise InfeasibleAction("Recharge must add positive energy")
            battery = min(p.battery, action.target_battery)
            end += charged * p.inverse_charge_rate
            if end <= state.time + EPS:
                raise InfeasibleAction("Charging action must advance time")
        after = replace(state, location=destination, time=end, battery=battery, load=load,
                        departed=state.departed or traveled > EPS or action.kind == "serve",
                        finished=action.kind == "return", status="finished" if action.kind == "return" else "idle",
                        current_committed_action=None, route_history=state.route_history + (destination.id,),
                        served_customers=state.served_customers + ((served,) if served else ()),
                        distance_travelled=state.distance_travelled + traveled,
                        charging_time=state.charging_time + charged * p.inverse_charge_rate,
                        waiting_time=state.waiting_time + start - arrival)
    if after.time > infra.depot.due + EPS:
        raise InfeasibleAction("Depot operating horizon exceeded", InfeasibilityReason.DEPOT_HORIZON)
    if require_return:
        safe = escape(after, infra)
        if safe is None or safe.completion > infra.depot.due + EPS:
            raise InfeasibleAction("No feasible return to depot", InfeasibilityReason.UNREACHABLE_SAFE_CONTINUATION)
    return Transition(state, after, action, traveled, charged, arrival, start, served)


def try_transition(state: VehicleState, action: Action, observation: Observation,
                   require_return: bool = True) -> Transition | RejectedTransition:
    try:
        return transition(state, action, observation, require_return)
    except InfeasibleAction as error:
        return RejectedTransition(error.reason, str(error))


def nearest_reachable_safe_node(state: VehicleState, infra: Infrastructure) -> Location | None:
    nodes = [node for node in (infra.depot,) + infra.stations
             if distance(state.location, node) * infra.parameters.consumption <= state.battery + EPS]
    return min(nodes, key=lambda node: (distance(state.location, node), node.id), default=None)


def safe_continuation(state: VehicleState, infra: Infrastructure) -> bool:
    result = escape(state, infra)
    return result is not None and result.completion <= infra.depot.due + EPS


TransitionResult = Transition


def escape_action(state: VehicleState, infra: Infrastructure) -> Action:
    route = escape(state, infra)
    if route is None or route.completion > infra.depot.due + EPS:
        raise InfeasibleAction("No feasible return")
    first = route.path[0]
    if first.kind == "d":
        return Action("return", first.id)
    p = infra.parameters
    arrival_battery = max(0.0, state.battery - p.consumption * distance(state.location, first))
    required = max(0.0, route.distance * p.consumption - state.battery)
    target = min(p.battery, arrival_battery + required)
    return Action("charge", first.id, target_battery=target)

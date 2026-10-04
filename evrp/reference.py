"""Deterministic multi-start insertion reference heuristic, without optimality claims."""

from dataclasses import asdict, dataclass
from functools import lru_cache
from collections import OrderedDict
import heapq
import itertools
import json
from pathlib import Path
import random

from .instance import Instance, Location
from .model import (Action, EPS, InfeasibleAction, InfeasibilityReason, Observation,
                    Transition, VehicleState, transition)
from .storage import identifier, save_json
from .versions import REFERENCE_SOLVER_VERSION


@dataclass(frozen=True)
class ReferenceConfig:
    multistarts: int = 3
    improvement_passes: int = 1
    seed: int = 0
    label_limit: int = 24

    def __post_init__(self):
        if self.multistarts < 1 or self.improvement_passes < 0 or self.label_limit < 1:
            raise ValueError("Invalid reference search budget")


@dataclass(frozen=True)
class RouteTrace:
    customers: tuple[str, ...]
    steps: tuple[Transition, ...]

    @property
    def distance(self) -> float:
        return sum(step.distance for step in self.steps)


@dataclass(frozen=True)
class ReferenceSchedule:
    base_instance: str
    instance_sha256: str
    config: ReferenceConfig
    routes: tuple[RouteTrace, ...]
    reference_solver_version: str = REFERENCE_SOLVER_VERSION

    @property
    def identifier(self) -> str:
        return identifier(asdict(self))

    @property
    def fleet_size(self) -> int:
        return len(self.routes)

    @property
    def total_distance(self) -> float:
        return sum(route.distance for route in self.routes)

    @property
    def predecessor_departures(self) -> dict[str, float]:
        return {s.served: s.before.time for r in self.routes for s in r.steps if s.served}

    def save(self, path: str | Path) -> None:
        save_json(path, {**asdict(self), "identifier": self.identifier,
                         "fleet_size": self.fleet_size, "total_distance": self.total_distance})

    @classmethod
    def load(cls, path: str | Path, instance: Instance) -> "ReferenceSchedule":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("reference_solver_version") != REFERENCE_SOLVER_VERSION:
            raise ReferenceFailure("Stale reference solver version; regenerate reference")
        def vehicle(raw):
            raw = dict(raw)
            raw["location"] = Location(**raw["location"])
            for key in ("route_history", "served_customers"):
                raw[key] = tuple(raw[key])
            if raw["current_committed_action"]:
                raw["current_committed_action"] = Action(**raw["current_committed_action"])
            return VehicleState(**raw)
        routes = []
        for route in data["routes"]:
            steps = []
            for raw in route["steps"]:
                raw = dict(raw)
                raw["before"], raw["after"] = vehicle(raw["before"]), vehicle(raw["after"])
                raw["action"] = Action(**raw["action"])
                steps.append(Transition(**raw))
            routes.append(RouteTrace(tuple(route["customers"]), tuple(steps)))
        result = cls(data["base_instance"], data["instance_sha256"], ReferenceConfig(**data["config"]), tuple(routes))
        if result.identifier != data["identifier"]:
            raise ReferenceFailure("Reference content hash mismatch")
        validate_reference(instance, result)
        return result


class ReferenceFailure(RuntimeError):
    pass


def initial_vehicle(instance: Instance, vehicle_id: int = 0) -> VehicleState:
    infra = instance.infrastructure
    return VehicleState(vehicle_id, infra.depot, infra.depot.ready,
                        infra.parameters.battery, infra.parameters.capacity,
                        route_history=(infra.depot.id,))


def full_charge_connection(state: VehicleState, goal: Action,
                           observation: Observation) -> tuple[Transition, ...] | None:
    """Repair a route gap, retaining nondominated full-SOC station labels.

    Feasible direct travel is shortest by the Euclidean triangle inequality.
    The repair is constructive, not an exact EVRPTW solver.
    """
    try:
        return (transition(state, goal, observation),)
    except InfeasibleAction as error:
        if error.reason in {InfeasibilityReason.CAPACITY, InfeasibilityReason.TIME_WINDOW,
                            InfeasibilityReason.DEPOT_HORIZON, InfeasibilityReason.INVALID_ACTION}:
            return None
    counter = itertools.count()
    queue = [(0.0, next(counter), state, ())]
    labels: dict[str, list[tuple[float, float]]] = {}
    best = None
    while queue:
        cost, _, current, steps = heapq.heappop(queue)
        if best and cost > best[0] + EPS:
            continue
        if steps:
            try:
                final = transition(current, goal, observation)
                candidate = (cost + final.distance, final.after.time, steps + (final,))
                if best is None or candidate[:2] < best[:2]:
                    best = candidate
            except InfeasibleAction:
                pass
        visited = {s.action.destination for s in steps}
        for station in observation.infrastructure.stations:
            if station.id in visited:
                continue
            try:
                step = transition(current, Action("charge", station.id,
                                  observation.infrastructure.parameters.battery), observation)
            except InfeasibleAction:
                continue
            value = (step.after.time, cost + step.distance)
            existing = labels.setdefault(station.id, [])
            if any(t <= value[0] + EPS and d <= value[1] + EPS for t, d in existing):
                continue
            existing[:] = [(t, d) for t, d in existing if not (value[0] <= t + EPS and value[1] <= d + EPS)]
            existing.append(value)
            heapq.heappush(queue, (value[1], next(counter), step.after, steps + (step,)))
    return best[2] if best else None


def evaluate_route(instance: Instance, sequence: tuple[str, ...], vehicle_id: int = 0,
                   label_limit: int = 24, prefix_cache=None) -> RouteTrace | None:
    if len(set(sequence)) != len(sequence):
        return None
    observation = Observation(instance.infrastructure.depot.ready, instance.infrastructure, instance.customers)
    if sum(c.demand for c in instance.customers if c.id in sequence) > instance.infrastructure.parameters.capacity + EPS:
        return None
    state = initial_vehicle(instance, vehicle_id)
    labels = [(state, ())]
    actions = tuple(Action("serve", c) for c in sequence) + (Action("return", state.location.id),)
    offset = 0
    if prefix_cache is not None:
        for length in range(len(sequence), 0, -1):
            key = (instance, vehicle_id, label_limit, sequence[:length])
            if key in prefix_cache:
                labels = list(prefix_cache[key])
                prefix_cache.move_to_end(key)
                if not labels:
                    return None
                offset = length
                break

    def dominates(a, b):
        return (a.time <= b.time + EPS and a.battery >= b.battery - EPS
                and a.distance_travelled <= b.distance_travelled + EPS)

    for index, action in enumerate(actions[offset:], start=offset):
        goal_labels, station_labels = [], {}
        queue = list(labels)
        while queue:
            current, trace = queue.pop()
            try:
                step = transition(current, action, observation)
                if not any(dominates(s, step.after) for s, _ in goal_labels):
                    goal_labels = [(s, tr) for s, tr in goal_labels if not dominates(step.after, s)]
                    goal_labels.append((step.after, trace + (step,)))
            except InfeasibleAction as error:
                if error.reason in {InfeasibilityReason.CAPACITY, InfeasibilityReason.TIME_WINDOW,
                                    InfeasibilityReason.DEPOT_HORIZON, InfeasibilityReason.INVALID_ACTION}:
                    continue
            for station in instance.infrastructure.stations:
                try:
                    step = transition(current, Action("charge", station.id,
                                      instance.infrastructure.parameters.battery), observation)
                except InfeasibleAction:
                    continue
                previous = station_labels.setdefault(station.id, [])
                if any(dominates(s, step.after) for s in previous):
                    continue
                previous[:] = [s for s in previous if not dominates(step.after, s)]
                previous.append(step.after)
                queue.append((step.after, trace + (step,)))
        if not goal_labels:
            if prefix_cache is not None and action.kind == "serve":
                prefix_cache[(instance, vehicle_id, label_limit, sequence[:index+1])] = ()
                while len(prefix_cache) > 512:
                    prefix_cache.popitem(last=False)
            return None
        # Exhaustive Pareto labels for C5 validation; bounded search for larger cases.
        labels = sorted(goal_labels, key=lambda pair: (pair[0].distance_travelled, pair[0].time, -pair[0].battery))
        if len(instance.customers) > 5:
            labels = labels[:label_limit]
        if prefix_cache is not None and action.kind == "serve":
            key = (instance, vehicle_id, label_limit, sequence[:index+1])
            prefix_cache[key] = tuple(labels)
            prefix_cache.move_to_end(key)
            while len(prefix_cache) > 512:
                prefix_cache.popitem(last=False)
    _, trace = min(labels, key=lambda pair: (pair[0].distance_travelled, pair[0].time))
    return RouteTrace(sequence, trace)


def validate_reference(instance: Instance, schedule: ReferenceSchedule) -> None:
    if schedule.reference_solver_version != REFERENCE_SOLVER_VERSION:
        raise ReferenceFailure("Stale reference solver version")
    if (schedule.base_instance, schedule.instance_sha256) != (instance.name, instance.sha256):
        raise ReferenceFailure("Reference schedule is bound to another instance")
    seen = []
    observation = Observation(instance.infrastructure.depot.ready, instance.infrastructure, instance.customers)
    for k, route in enumerate(schedule.routes):
        state, served = initial_vehicle(instance, k), []
        for stored in route.steps:
            actual = transition(state, stored.action, observation)
            if actual != stored:
                raise ReferenceFailure("Reference trace differs from the common transition engine")
            if actual.served:
                served.append(actual.served)
            state = actual.after
        if not state.finished or state.location != instance.infrastructure.depot or tuple(served) != route.customers:
            raise ReferenceFailure("Reference route is incomplete")
        seen.extend(served)
    if len(seen) != len(set(seen)) or set(seen) != {c.id for c in instance.customers}:
        raise ReferenceFailure("Reference must serve every customer exactly once")


@lru_cache(maxsize=64)
def solve_reference(instance: Instance, config: ReferenceConfig = ReferenceConfig()) -> ReferenceSchedule:
    prefixes = OrderedDict()
    @lru_cache(maxsize=40000)
    def evaluate(sequence: tuple[str, ...]) -> RouteTrace | None:
        return evaluate_route(instance, sequence, label_limit=config.label_limit, prefix_cache=prefixes)

    if len(instance.customers) <= 5:
        ids = tuple(sorted(c.id for c in instance.customers))
        routes_by_set = {}
        for size in range(1, len(ids) + 1):
            for sequence in itertools.permutations(ids, size):
                route = evaluate(sequence)
                key = frozenset(sequence)
                if route and (key not in routes_by_set or route.distance < routes_by_set[key].distance):
                    routes_by_set[key] = route

        @lru_cache(None)
        def partition(remaining):
            if not remaining:
                return (0, 0.0, ())
            first = min(remaining)
            best = None
            for subset, route in routes_by_set.items():
                if first not in subset or not subset <= remaining:
                    continue
                tail = partition(remaining - subset)
                if tail is not None:
                    candidate = (1 + tail[0], route.distance + tail[1], (route.customers,) + tail[2])
                    if best is None or candidate < best:
                        best = candidate
            return best

        best = partition(frozenset(ids))
        if best is None:
            raise ReferenceFailure(f"No feasible reference for {instance.name}")
        result = ReferenceSchedule(instance.name, instance.sha256, config,
                                   tuple(evaluate_route(instance, r, k) for k, r in enumerate(best[2])))
        validate_reference(instance, result)
        return result

    best, failures = None, set()
    for start in range(config.multistarts):
        rng = random.Random(config.seed + start)
        ordered = sorted(instance.customers, key=lambda c: (c.due if start == 0 else
                         c.due + rng.uniform(-0.15, 0.15) * instance.infrastructure.depot.due, c.id))
        routes: list[tuple[str, ...]] = []
        failed = False
        for customer in ordered:
            options = []
            for r, sequence in enumerate(routes):
                old = evaluate(sequence)
                for position in range(len(sequence) + 1):
                    proposed = sequence[:position] + (customer.id,) + sequence[position:]
                    candidate = evaluate(proposed)
                    if candidate:
                        options.append((candidate.distance - old.distance, r, position, proposed))
            if options:
                _, r, _, proposed = min(options)
                routes[r] = proposed
            elif evaluate((customer.id,)):
                routes.append((customer.id,))
            else:
                failures.add(customer.id)
                failed = True
                break
        if failed:
            continue
        # Targeted route elimination: reinsert all customers of a short route.
        for source in sorted(range(len(routes)), key=lambda k: len(routes[k]), reverse=True):
            if source >= len(routes):
                continue
            trial = routes[:source] + routes[source + 1:]
            eliminated = True
            for customer in routes[source]:
                options = []
                for r, route in enumerate(trial):
                    for pos in range(len(route) + 1):
                        seq = route[:pos] + (customer,) + route[pos:]
                        candidate = evaluate(seq)
                        if candidate:
                            options.append((candidate.distance - evaluate(route).distance, r, seq))
                if not options:
                    eliminated = False
                    break
                _, r, seq = min(options)
                trial[r] = seq
            if eliminated:
                routes = trial
        for _ in range(config.improvement_passes):
            baseline = (len(routes), sum(evaluate(r).distance for r in routes))
            improvement = None
            for source, sequence in enumerate(routes):
                for index, customer in enumerate(sequence):
                    remainder = sequence[:index] + sequence[index + 1:]
                    if remainder and evaluate(remainder) is None:
                        continue
                    for target, destination in enumerate(routes):
                        if target == source:
                            destination = remainder
                        for position in range(len(destination) + 1):
                            proposed = destination[:position] + (customer,) + destination[position:]
                            if evaluate(proposed) is None:
                                continue
                            changed = list(routes)
                            changed[source], changed[target] = remainder, proposed
                            changed = [r for r in changed if r]
                            score = (len(changed), sum(evaluate(r).distance for r in changed))
                            if score[0] < baseline[0] or (score[0] == baseline[0] and score[1] < baseline[1] - EPS):
                                improvement = changed
                                break
                        if improvement:
                            break
                    if improvement:
                        break
                if improvement:
                    break
            if improvement is None:
                break
            routes = improvement
        score = (len(routes), sum(evaluate(r).distance for r in routes))
        if best is None or score < best[0]:
            best = (score, routes)
    if best is None:
        raise ReferenceFailure(f"No feasible reference for {instance.name}; failed customers: {sorted(failures)}")
    traces = tuple(evaluate_route(instance, route, k, config.label_limit) for k, route in enumerate(best[1]))
    result = ReferenceSchedule(instance.name, instance.sha256, config, traces)
    validate_reference(instance, result)
    return result

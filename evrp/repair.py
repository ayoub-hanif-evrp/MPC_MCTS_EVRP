"""Deterministic regret-2 insertion into a fixed fleet's executable suffixes.

Only the supplied observation is visible. Origins are measured ready states or
states AFTER immutable busy actions, never the states before those actions.
Replay is independent of the local MPC horizon. Construction is conservative:
direct travel, bounded MPC single-station bridges, then full-charge connections.
It does not backtrack over earlier charging decisions or optimize partial-charge
multi-hop paths, so construction failure is not a proof of infeasibility.
"""

from dataclasses import dataclass, replace
from math import inf, isfinite

from .model import (EPS, Action, InfeasibleAction, InfeasibilityReason,
                    Observation, VehicleState)
from .mpc import MPCConfig, MPCPlanningProblem, MPCProposal, action_key
from .reference import full_charge_connection


def _valid_origin(state: VehicleState, observation: Observation) -> bool:
    p = observation.infrastructure.parameters
    return (not state.finished and state.current_committed_action is None
            and all(isfinite(v) for v in (state.time, state.battery, state.load))
            and state.time >= observation.time - EPS
            and state.time <= observation.infrastructure.depot.due + EPS
            and -EPS <= state.battery <= p.battery + EPS
            and -EPS <= state.load <= p.capacity + EPS)


def _evaluate(state, actions, observation, config):
    if not actions or not _valid_origin(state, observation):
        return None
    problem = MPCPlanningProblem(observation, state, config)
    predicted, distance, starts = problem.initial, 0.0, {}
    try:
        # predict enforces the plant/charging policy; done would impose Hp.
        for action in actions:
            predicted, step = problem.predict(predicted, action)
            distance += step.distance
            if step.served is not None:
                starts[step.served] = step.service_start
        proposal = problem.proposal_from_state(actions, predicted, distance)
    except InfeasibleAction:
        return None
    if not isfinite(proposal.cost):
        return None
    return proposal, starts


def route_proposal(state: VehicleState, actions: tuple[Action, ...],
                   observation: Observation, config: MPCConfig) -> MPCProposal | None:
    """Replay a full suffix, returning its finite distance including safe return.

    Return None for empty or infeasible actions, hidden/committed/duplicate service,
    or an invalid origin. WAIT/RETURN actions can be validated here, but repair's
    retained routes must end at their last service. No prediction-horizon truncation
    or temporary horizon increase is used. The supplied state is never mutated.
    """
    evaluated = _evaluate(state, tuple(actions), observation, config)
    return evaluated[0] if evaluated is not None else None


def build_route(state: VehicleState, customer_sequence: tuple[str, ...],
                observation: Observation, config: MPCConfig) -> tuple[Action, ...] | None:
    """Build actions through the last service, or None if construction fails.

    An empty sequence returns () only when the origin has a feasible safe return.
    Customer order is fixed. A bridge minimizes distance, then completion time,
    then action keys; full charging obeys the same policy as local MPC. This helper
    uses no reference schedules and no unreleased customer information.
    """
    sequence = tuple(customer_sequence)
    if (not _valid_origin(state, observation) or len(set(sequence)) != len(sequence)
            or any(c not in observation.customer_by_id or c in observation.committed_ids
                   or c in state.served_customers for c in sequence)):
        return None
    problem = MPCPlanningProblem(observation, state, config)
    predicted, actions = problem.initial, ()
    energy_failures = {InfeasibilityReason.BATTERY,
                       InfeasibilityReason.UNREACHABLE_SAFE_CONTINUATION}
    for customer in sequence:
        goal = Action("serve", customer)
        try:
            predicted, _ = problem.predict(predicted, goal)
            actions += (goal,)
            continue
        except InfeasibleAction as error:
            if error.reason not in energy_failures:
                return None

        choices = []
        # Aim bounded MPC charge candidates at this gap, not unrelated work.
        candidates = problem.charge_actions(replace(predicted, remaining=frozenset({customer})))
        for charge in candidates:
            try:
                charged, first = problem.predict(predicted, charge)
                served, last = problem.predict(charged, goal)
            except InfeasibleAction:
                continue
            bridge = (charge, goal)
            choices.append((first.distance + last.distance, served.vehicle.time,
                            tuple(action_key(a) for a in bridge), served, bridge))
        if choices:
            _, _, _, predicted, bridge = min(choices, key=lambda row: row[:3])
        else:
            connection = full_charge_connection(predicted.vehicle, goal, observation)
            if connection is None:
                return None
            bridge = tuple(step.action for step in connection)
            try:
                for action in bridge:
                    predicted, _ = problem.predict(predicted, action)
            except InfeasibleAction:
                return None
        actions += bridge
    if not isfinite(problem.terminal_cost(predicted)):
        return None
    return actions


@dataclass(frozen=True)
class _Insertion:
    vehicle_id: int
    position: int
    proposal: MPCProposal
    incremental_cost: float
    slack: float
    new_activation: bool

    @property
    def key(self):
        # Activation is only an exact-distance tie break, never a penalty.
        return (self.incremental_cost, self.new_activation, self.vehicle_id,
                self.position, tuple(action_key(a) for a in self.proposal.actions))


def regret_repair(origins: dict[int, VehicleState], routes: dict[int, tuple[Action, ...]],
                  observation: Observation, config: MPCConfig
                  ) -> tuple[dict[int, tuple[Action, ...]], list[dict]]:
    """Insert released unassigned requests without changing fleet or ownership.

    The output has exactly the origins' keys; absent input routes mean empty routes.
    Finished vehicles and unknown route keys are input errors. Duplicate, hidden or
    committed route customers are also errors: reconciliation belongs to the caller.
    An infeasible incumbent is retained unchanged and its owner is not extended.

    Records contain customer, vehicle_id, zero-based customer position,
    incremental_cost, regret2 (null for a unique option), feasible_options,
    remaining_tw_slack (at the cheapest insertion), and predicted new_activation.
    The activation flag describes an additional planned departure; physical fleet
    activation changes only when the caller dispatches. Neither input is mutated.

    Each customer/position/vehicle is one option, irrespective of charging variants.
    Only the changed owner's insertion cache is invalidated after an insertion.
    There are at most as many iterations as initially released unassigned customers.
    """
    if set(routes) - set(origins):
        raise ValueError("Route keys must belong to the fixed fleet origins")
    if any(k != state.id or state.finished for k, state in origins.items()):
        raise ValueError("Origins must have matching vehicle IDs and never be finished")
    updated = {k: tuple(routes.get(k, ())) for k in sorted(origins)}
    owned = set()
    for actions in updated.values():
        if actions and (actions[-1].kind != "serve"
                        or any(a.kind == "return" for a in actions)):
            raise ValueError("Retained routes must end at the last service, without RETURN")
        for action in actions:
            if action.kind != "serve":
                continue
            customer = action.destination
            if customer in owned:
                raise ValueError("Duplicate customer ownership in input routes")
            if customer not in observation.customer_by_id or customer in observation.committed_ids:
                raise ValueError("Input routes contain hidden or committed customers")
            owned.add(customer)

    served = {c for state in origins.values() for c in state.served_customers}
    pending = set(observation.customer_by_id) - owned - observation.committed_ids - served
    baselines = {}
    for k, actions in updated.items():
        state = origins[k]
        if not _valid_origin(state, observation):
            continue
        if actions:
            proposal = route_proposal(state, actions, observation, config)
            if proposal is not None:
                baselines[k] = proposal.cost
        else:
            problem = MPCPlanningProblem(observation, state, config)
            cost = problem.terminal_cost(problem.initial)
            if isfinite(cost):
                baselines[k] = cost

    cache: dict[int, dict[str, tuple[_Insertion, ...]]] = {k: {} for k in baselines}
    records = []
    for _ in range(len(pending)):
        ranked = []
        for customer_id in sorted(pending):
            customer = observation.customer_by_id[customer_id]
            options = []
            for k in baselines:
                if customer_id not in cache[k]:
                    sequence = tuple(a.destination for a in updated[k] if a.kind == "serve")
                    insertions = []
                    for position in range(len(sequence) + 1):
                        proposed = sequence[:position] + (customer_id,) + sequence[position:]
                        actions = build_route(origins[k], proposed, observation, config)
                        if actions is None:
                            continue
                        evaluated = _evaluate(origins[k], actions, observation, config)
                        if evaluated is None:
                            continue
                        proposal, starts = evaluated
                        insertions.append(_Insertion(
                            k, position, proposal, proposal.cost - baselines[k],
                            customer.due - starts[customer_id],
                            not origins[k].departed and not updated[k]))
                    cache[k][customer_id] = tuple(insertions)
                options.extend(cache[k][customer_id])
            if not options:
                continue
            options.sort(key=lambda option: option.key)
            best = options[0]
            regret = options[1].incremental_cost - best.incremental_cost if len(options) > 1 else inf
            priority = (len(options) != 1, -regret, best.slack, customer.due, customer_id)
            ranked.append((priority, customer_id, best, regret, len(options)))
        if not ranked:
            break
        _, customer_id, best, regret, count = min(ranked, key=lambda row: row[0])
        k = best.vehicle_id
        updated[k] = best.proposal.actions
        baselines[k] = best.proposal.cost
        cache[k].clear()
        pending.remove(customer_id)
        records.append(dict(vehicle_id=k, customer=customer_id, position=best.position,
                            incremental_cost=best.incremental_cost, regret2=regret if isfinite(regret) else None,
                            feasible_options=count, remaining_tw_slack=best.slack,
                            new_activation=best.new_activation))
    return updated, records


def compact_unused_routes(origins: dict[int, VehicleState], routes: dict[int, tuple[Action, ...]],
                          observation: Observation, config: MPCConfig
                          ) -> tuple[dict[int, tuple[Action, ...]], list[dict]]:
    """One deterministic service-preserving pass moving unused-EV routes to active EVs."""
    updated = {k: tuple(routes.get(k, ())) for k in sorted(origins)}
    transfers = []
    for source in sorted(updated):
        if origins[source].departed or not updated[source]:
            continue
        customers = tuple(a.destination for a in updated[source] if a.kind == "serve")
        trial = updated.copy()
        moved = []
        for customer in customers:
            options = []
            for target in sorted(trial):
                if target == source or not origins[target].departed:
                    continue
                sequence = tuple(a.destination for a in trial[target] if a.kind == "serve")
                if trial[target]:
                    current = route_proposal(origins[target], trial[target], observation, config)
                    if current is None:
                        continue
                    baseline = current.cost
                else:
                    problem = MPCPlanningProblem(observation, origins[target], config)
                    baseline = problem.terminal_cost(problem.initial)
                if not isfinite(baseline):
                    continue
                for position in range(len(sequence) + 1):
                    actions = build_route(origins[target], sequence[:position] + (customer,) + sequence[position:],
                                          observation, config)
                    if actions is None:
                        continue
                    proposal = route_proposal(origins[target], actions, observation, config)
                    if proposal is not None:
                        options.append((proposal.cost - baseline, target, position, actions))
            if not options:
                break
            _, target, position, actions = min(options, key=lambda row: (row[0], row[1], row[2],
                                                                         tuple(action_key(a) for a in row[3])))
            trial[target] = actions
            moved.append((customer, target))
        if len(moved) == len(customers):
            trial[source] = ()
            updated = trial
            transfers.append(dict(from_vehicle=source, customers=list(customers),
                                  to_vehicles={customer: target for customer, target in moved}))
    return updated, transfers

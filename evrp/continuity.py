"""Opt-in, executable route reservations, never forecasts of hidden requests."""

from dataclasses import replace
from math import isfinite

from .model import EPS, Action, InfeasibleAction
from .mpc import MPCPlanningProblem, PlanningResult, proposal_key


def service_tail(proposal):
    """Keep only the unexecuted prefix through the last planned customer."""
    last = max((i for i, a in enumerate(proposal.actions) if a.kind == "serve"), default=0)
    return proposal.actions[1:last + 1]


def reserved_customers(tails, excluding=None):
    return frozenset(a.destination for k, actions in tails.items() if k != excluding
                     for a in actions if a.kind == "serve")


def route_observation(observation, tails, vehicle_id=None):
    reserved = reserved_customers(tails, excluding=vehicle_id)
    return replace(observation, customers=tuple(c for c in observation.customers if c.id not in reserved))


def preserve_continuation(result, state, observation, config, actions):
    if not actions:
        return result
    # Replaying the retained suffix is a feasibility certificate at the measured
    # state. Do not silently discard a promise when a search fails to recover it.
    problem = MPCPlanningProblem(observation, state, config)
    retained = problem.proposal(actions)
    required = set(retained.unique_predicted_customer_set)
    proposals = [p for p in result.proposals if required <= set(p.unique_predicted_customer_set)]
    if not any(p.actions == retained.actions for p in proposals):
        proposals.append(retained)
    return PlanningResult(tuple(sorted(proposals, key=proposal_key)), retained,
                          result.statistics, result.evaluated_proposals)


def assert_unique_routes(tails):
    customers = [a.destination for actions in tails.values() for a in actions if a.kind == "serve"]
    if len(customers) != len(set(customers)):
        raise RuntimeError("A future customer was reserved by multiple executable routes")


def insert_known_requests(states, busy, observation, config, tails):
    """Cheapest feasible insertion, due-date order, with no action preemption.

    A busy EV's immutable action is executed first. Its resulting state is the
    prediction origin; only requests already revealed NOW are considered.
    """
    reserved = reserved_customers(tails)
    free = sorted((c for c in observation.customers if c.id not in reserved), key=lambda c: (c.due, c.id))
    inserted = []
    for customer in free:
        choices = []
        for vehicle_id, measured in sorted(states.items()):
            state = busy[vehicle_id].after if vehicle_id in busy else measured
            if state.finished or not state.departed or state.time < observation.time - EPS:
                continue
            actions = tails.get(vehicle_id, ())
            if sum(a.kind == "serve" for a in actions) >= config.prediction_horizon:
                continue
            obs = replace(route_observation(observation, tails, vehicle_id), time=state.time)
            problem = MPCPlanningProblem(obs, state, config)
            baseline = problem.proposal(actions).cost if actions else problem.terminal_cost(problem.initial)
            for position in range(len(actions) + 1):
                proposed = actions[:position] + (Action("serve", customer.id),) + actions[position:]
                try:
                    certificate = problem.proposal(proposed)
                except InfeasibleAction:
                    continue
                if isfinite(certificate.cost):
                    choices.append((certificate.cost - baseline, certificate.completion_time,
                                    vehicle_id, position, proposed))
        if choices:
            _, _, vehicle_id, _, proposed = min(choices)
            tails[vehicle_id] = proposed
            inserted.append(dict(vehicle_id=vehicle_id, customer=customer.id))
    assert_unique_routes(tails)
    return inserted

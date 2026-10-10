"""Executable route ownership and finite-horizon candidate reconciliation."""

from dataclasses import replace

from .model import InfeasibleAction
from .mpc import PlanningResult, proposal_key


def service_prefix(actions):
    last = max((i for i, a in enumerate(actions) if a.kind == "serve"), default=-1)
    return actions[:last + 1]


def service_tail(proposal):
    return service_prefix(proposal.actions)[1:]


def reserved_customers(tails, excluding=None):
    return frozenset(a.destination for k, actions in tails.items() if k != excluding
                     for a in actions if a.kind == "serve")


def route_observation(observation, tails, vehicle_id=None):
    reserved = reserved_customers(tails, excluding=vehicle_id)
    return replace(observation, customers=tuple(c for c in observation.customers if c.id not in reserved))


def preserve_continuation(result, state, observation, config, actions):
    if not actions:
        return result
    from .repair import build_route, route_proposal
    retained = route_proposal(state, actions, observation, config)
    if retained is None:
        raise RuntimeError("Retained route became infeasible; commitments cannot be discarded")
    required = tuple(a.destination for a in actions if a.kind == "serve")
    proposals = []
    for p in result.proposals:
        if not service_prefix(p.actions):
            continue
        if set(required) <= set(p.unique_predicted_customer_set):
            proposals.append(p)
            continue
        # Optimize the finite prefix, then preserve remaining obligations in order.
        sequence = p.predicted_customer_sequence + tuple(c for c in required if c not in p.unique_predicted_customer_set)
        try:
            merged = build_route(state, sequence, observation, config)
            if merged is not None:
                candidate = route_proposal(state, merged, observation, config)
                if candidate is not None:
                    proposals.append(candidate)
        except InfeasibleAction:
            continue
    proposals.append(retained)
    unique = {}
    for p in sorted(proposals, key=proposal_key):
        unique.setdefault(p.actions, p)
    return PlanningResult(tuple(unique.values()), retained, result.statistics, result.evaluated_proposals)


def assert_unique_routes(tails):
    customers = [a.destination for actions in tails.values() for a in actions if a.kind == "serve"]
    if len(customers) != len(set(customers)):
        raise RuntimeError("A future customer was reserved by multiple executable routes")

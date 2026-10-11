"""Soft route incumbents and temporary ownership while actions are busy."""

from dataclasses import replace

from .mpc import PlanningResult


def service_prefix(actions):
    last = max((i for i, a in enumerate(actions) if a.kind == "serve"), default=-1)
    return actions[:last + 1]


def service_tail(proposal):
    return service_prefix(proposal.actions)[1:]


def reserved_customers(tails, excluding=None):
    return frozenset(a.destination for k, actions in tails.items() if k != excluding
                     for a in actions if a.kind == "serve")


def route_observation(observation, frozen_tails, vehicle_id=None):
    reserved = reserved_customers(frozen_tails, excluding=vehicle_id)
    return replace(observation, customers=tuple(c for c in observation.customers if c.id not in reserved))


def with_soft_incumbent(result, state, observation, config, actions):
    if not actions:
        return result
    from .repair import route_proposal
    retained = route_proposal(state, actions, observation, config)
    if retained is None:
        return result
    proposals = list(result.proposals)
    if all(p.actions != retained.actions for p in result.candidates):
        proposals.append(retained)
    return PlanningResult(tuple(proposals), result.fallback, result.statistics, result.evaluated_proposals)


def assert_unique_routes(tails):
    customers = [a.destination for actions in tails.values() for a in actions if a.kind == "serve"]
    if len(customers) != len(set(customers)):
        raise RuntimeError("A future customer was reserved by multiple executable routes")

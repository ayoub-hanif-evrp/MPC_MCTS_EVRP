"""Opt-in, executable route reservations, never forecasts of hidden requests."""

from dataclasses import replace

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

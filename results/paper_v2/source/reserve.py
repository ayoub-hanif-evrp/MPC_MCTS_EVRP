"""Exchangeable depot proposals; no physical EV exists until one is selected."""

from dataclasses import replace

from .model import VehicleState
from .mpc import MPCPlanningProblem, PlanningResult


def depot_template(observation):
    infra = observation.infrastructure
    return VehicleState(-1, infra.depot, observation.time, infra.parameters.battery,
                        infra.parameters.capacity, route_history=(infra.depot.id,),
                        waiting_time=observation.time-infra.depot.ready)


def bind_proposal(proposal, vehicle_id):
    end = replace(proposal.predicted_end_state, id=vehicle_id) if proposal.predicted_end_state else None
    return replace(proposal, vehicle_id=vehicle_id, predicted_end_state=end)


def reserve_options(result, observation, config, pending_targets=frozenset()):
    problem = MPCPlanningProblem(observation, depot_template(observation), config)
    idle = problem.proposal((problem.fallback(problem.initial),))
    # All evaluated distinct first actions, not independent randomized EV searches.
    proposals = result.evaluated_proposals or result.proposals
    options, anchors = {}, {}
    for proposal in proposals:
        if proposal.predicted_service_count and proposal.first.kind in {"serve", "charge"}:
            anchor = proposal.predicted_customer_sequence[0]
            if anchor in pending_targets:
                continue
            previous = anchors.get(anchor)
            if previous is None or (previous.first.kind != "serve" and proposal.first.kind == "serve"):
                anchors[anchor] = proposal
    for proposal in anchors.values():
        key = -len(options)-1
        options[key] = PlanningResult((bind_proposal(proposal, key),), bind_proposal(idle, key))
    return options

"""Online baselines sharing the MPC action model and physical transition engine."""

from dataclasses import replace
from time import perf_counter

from .model import Action, InfeasibleAction
from .mpc import MPCConfig, MPCPlanningProblem, PlanningResult, SearchStatistics


def greedy_plan(state, observation, config: MPCConfig) -> PlanningResult:
    start = perf_counter()
    problem = MPCPlanningProblem(observation, state, replace(config, prediction_horizon=1))
    actions = problem.actions(problem.initial)
    serving = [a for a in actions if a.kind == "serve"]
    ranked = sorted(serving, key=lambda a: problem.customer_rank(problem.initial, a))
    proposals = [problem.proposal((a,)) for a in ranked[:config.top_l]]
    if not proposals:
        options = []
        for action in actions:
            if action.kind != "charge":
                continue
            following, _ = problem.predict(problem.initial, action)
            for customer in (problem.customer_pool(following) if config.action_space_reduction else observation.customers):
                serve = Action("serve", customer.id)
                try:
                    problem.predict(following, serve)
                    proposal = problem.proposal((action, serve))
                    options.append((problem.customer_rank(following, serve), proposal))
                except InfeasibleAction:
                    continue
        unique = {}
        for _, proposal in sorted(options, key=lambda pair: pair[0]):
            unique.setdefault(proposal.first, proposal)
        proposals = list(unique.values())[:config.top_l]
    fallback = problem.proposal((problem.fallback(problem.initial),))
    all_proposals = tuple(problem.proposal((a,)) for a in ranked) if ranked else tuple(proposals)
    return PlanningResult(tuple(proposals), fallback, SearchStatistics(elapsed=perf_counter() - start), all_proposals)


def independent_selection(plans: dict[int, PlanningResult], reserve_ids=frozenset(), reserve_count=0) -> tuple[dict, int]:
    selected, committed, conflicts = {}, set(), 0
    for vehicle_id, result in sorted(plans.items(), key=lambda item: (item[0] in reserve_ids, abs(item[0]))):
        proposal = result.proposals[0] if result.proposals else result.fallback
        if vehicle_id in reserve_ids and proposal.predicted_customer_sequence:
            if proposal.predicted_customer_sequence[0] in committed:
                proposal = result.fallback
        if proposal.first.kind == "serve":
            if proposal.first.destination in committed:
                conflicts += 1
                proposal = next((p for p in result.proposals
                                 if p.first.kind != "serve" or p.first.destination not in committed), result.fallback)
            if vehicle_id in reserve_ids and reserve_count <= 0:
                proposal = result.fallback
            if proposal.first.kind == "serve":
                committed.add(proposal.first.destination)
        if vehicle_id in reserve_ids and proposal.first.kind in {"serve", "charge"}:
            if reserve_count <= 0:
                proposal = result.fallback
            else:
                reserve_count -= 1
                committed.add(proposal.predicted_customer_sequence[0])
        selected[vehicle_id] = proposal
    return selected, conflicts

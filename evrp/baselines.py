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


def independent_selection(plans: dict[int, PlanningResult], exclusive_routes=True) -> tuple[dict, int]:
    selected, claimed, conflicts = {}, set(), 0
    for vehicle_id, result in sorted(plans.items()):
        choices = result.candidates
        def claims(p):
            return (set(p.unique_predicted_customer_set) if exclusive_routes else
                    {p.first.destination} if p.first.kind == "serve" else set())
        admissible = [p for p in choices if not claimed.intersection(claims(p))]
        if not admissible:
            raise RuntimeError("No conflict-free continuation for an existing route")
        proposal = admissible[0]
        conflicts += int(proposal != choices[0])
        claimed.update(claims(proposal))
        selected[vehicle_id] = proposal
    return selected, conflicts

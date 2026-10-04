"""UCT with bounded service-first reward and explicit lexicographic plan ranking."""

from dataclasses import asdict, dataclass, field, replace
from math import log, sqrt
import random
from time import perf_counter

from .model import Action, InfeasibleAction
from . import performance as perf
from .mpc import (MPCPlanningProblem, MPCState, PlanningResult, SearchStatistics,
                  action_key, proposal_key)


@dataclass
class Node:
    state: MPCState
    path: tuple[Action, ...] = ()
    prefix_cost: float = 0.0
    children: list["Node"] = field(default_factory=list)
    untried: list[Action] | None = None
    visits: int = 0
    value_sum: float = 0.0


def uct(child: Node, parent_visits: int, coefficient: float) -> float:
    if child.visits == 0:
        return float("inf")
    return child.value_sum / child.visits + coefficient * sqrt(log(max(1, parent_visits)) / child.visits)


class MCTSOptimizer:
    def solve(self, problem: MPCPlanningProblem, seed: int) -> PlanningResult:
        started = perf_counter()
        rng, cfg = random.Random(seed), problem.config
        root, best, cache = Node(problem.initial), {}, {}
        iterations, expanded = 0, 0

        def available(state):
            if state not in cache:
                cache[state] = problem.actions(state)
            return cache[state]

        def rollout_action(state, actions):
            serving = [a for a in actions if a.kind == "serve"]
            if serving:
                ranked = sorted(serving, key=lambda a: problem.customer_rank(state, a))
                return rng.choice(ranked[:min(3, len(ranked))])
            charging = []
            for action in actions:
                if action.kind != "charge":
                    continue
                next_state, step = problem.predict(state, action)
                possible = (problem.customer_pool(next_state) if cfg.action_space_reduction else
                            [c for c in problem.observation.customers if c.id in next_state.remaining])
                for customer in possible:
                    try:
                        _, service = problem.predict(next_state, Action("serve", customer.id))
                        charging.append((step.distance + service.distance, step.after.time, action))
                        break
                    except InfeasibleAction:
                        continue
            if charging:
                return min(charging, key=lambda item: item[:2])[2]
            return problem.fallback(state)

        while ((cfg.budget_mode == "iterations" and iterations < cfg.iterations) or
               (cfg.budget_mode == "wall_clock" and (iterations == 0 or perf_counter() - started < cfg.time_limit))):
            node, lineage = root, [root]
            measured = perf.stamp()
            while not problem.done(node.state):
                if node.untried is None:
                    node.untried = list(available(node.state))
                    rng.shuffle(node.untried)
                    node.untried.sort(key=lambda a: a.kind == "serve")
                if node.untried:
                    expansion_started = perf.stamp()
                    action = node.untried.pop()
                    state, step = problem.predict(node.state, action)
                    child = Node(state, node.path + (action,), node.prefix_cost + problem.stage_cost(step))
                    node.children.append(child)
                    node = child
                    lineage.append(node)
                    expanded += 1
                    perf.elapsed("mcts_expansion", expansion_started)
                    break
                if not node.children:
                    break
                node = max(node.children, key=lambda child: uct(child, node.visits, cfg.uct_c))
                lineage.append(node)
            state, path, cost = node.state, node.path, node.prefix_cost
            perf.elapsed("mcts_selection_expansion", measured)
            measured = perf.stamp()
            while not problem.done(state):
                actions = available(state)
                if not actions:
                    break
                action = rollout_action(state, actions)
                state, step = problem.predict(state, action)
                cost += problem.stage_cost(step)
                path += (action,)
            perf.elapsed("mcts_rollout", measured)
            if not path:
                break
            proposal = problem.proposal_from_state(path, state, cost)
            reward = problem.reward(proposal)
            measured = perf.stamp()
            for ancestor in lineage:
                ancestor.visits += 1
                ancestor.value_sum += reward
            perf.elapsed("mcts_backpropagation", measured)
            if path[0] not in best or proposal_key(proposal) < proposal_key(best[path[0]]):
                best[path[0]] = proposal
            iterations += 1
        visits = {child.path[0]: child.visits for child in root.children}
        values = {child.path[0]: child.value_sum / child.visits for child in root.children if child.visits}
        proposals = [replace(plan, visits=visits.get(plan.first, 0),
                             mcts_value_estimate=values.get(plan.first)) for plan in best.values()]
        proposals.sort(key=proposal_key)
        fallback = problem.proposal((problem.fallback(problem.initial),))
        stats = SearchStatistics(iterations, expanded, perf_counter() - started,
                                 tuple({"action": asdict(child.path[0]), "visits": child.visits,
                                        "mean_reward": child.value_sum / child.visits if child.visits else None}
                                       for child in sorted(root.children, key=lambda c: action_key(c.path[0]))))
        return PlanningResult(tuple(proposals[:cfg.top_l]), fallback, stats)

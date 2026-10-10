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


def _select_proposals(proposals, config):
    """Select from the best route per root action, retaining quality-first order."""
    remaining = sorted(proposals, key=proposal_key)
    if config.proposal_selection == "quality":
        return tuple(remaining[:config.top_l])
    selected, covered = [], set()
    while remaining and len(selected) < config.top_l:
        index = 0 if not selected else min(
            range(len(remaining)),
            key=lambda i: (-len(set(remaining[i].unique_predicted_customer_set) - covered),
                           proposal_key(remaining[i])))
        proposal = remaining.pop(index)
        selected.append(proposal)
        covered.update(proposal.unique_predicted_customer_set)
    return tuple(selected)


class MCTSOptimizer:
    def solve(self, problem: MPCPlanningProblem, seed: int) -> PlanningResult:
        """Wall-clock limits are cooperative; physics and finalization may overrun."""
        started = perf_counter()
        rng, cfg = random.Random(seed), problem.config
        root, best, cache = Node(problem.initial), {}, {}
        iterations, expanded = 0, 0
        deadline = started + cfg.time_limit if cfg.budget_mode == "wall_clock" else None

        def expired():
            return deadline is not None and perf_counter() >= deadline

        # Keep a validated incumbent even if setup consumes the entire budget.
        fallback = problem.proposal((problem.fallback(root.state),))

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
            fallback = problem.fallback(state)
            # A safe physical escape may revisit a station excluded by the
            # prediction's cycle guard. Rollouts must use the admissible set.
            return fallback if fallback in actions else min(actions, key=action_key)

        root_actions = available(root.state)
        iteration_limit = max(cfg.iterations, len(root_actions) if cfg.require_root_coverage else 0)
        while not expired() and (deadline is not None or iterations < iteration_limit):
            node, lineage = root, [root]
            measured = perf.stamp()
            while not problem.done(node.state) and not expired():
                if node.untried is None:
                    node.untried = list(available(node.state))
                    rng.shuffle(node.untried)
                    node.untried.sort(key=lambda a: a.kind == "serve")
                if expired():
                    break
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
            while not problem.done(state) and not expired():
                actions = available(state)
                if not actions or expired():
                    break
                action = rollout_action(state, actions)
                if expired():
                    break
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
        visits = {child.path[0]: child.visits for child in root.children if child.visits}
        values = {child.path[0]: child.value_sum / child.visits for child in root.children if child.visits}
        proposals = [replace(plan, visits=visits.get(plan.first, 0),
                             mcts_value_estimate=values.get(plan.first)) for plan in best.values()]
        proposals.sort(key=proposal_key)
        selected = _select_proposals(proposals, cfg)
        root_statistics = tuple({"action": asdict(child.path[0]), "visits": child.visits,
                                 "mean_reward": child.value_sum / child.visits if child.visits else None}
                                for child in sorted(root.children, key=lambda c: action_key(c.path[0])))
        elapsed = perf_counter() - started
        overrun = max(0.0, elapsed - cfg.time_limit) if deadline is not None else 0.0
        stats = SearchStatistics(iterations, expanded, elapsed, root_statistics,
                                 len(root_actions), len(visits),
                                 min((visits.get(a, 0) for a in root_actions), default=0),
                                 len(visits) / len(root_actions) if root_actions else 1.0,
                                 "cooperative" if deadline is not None else "none", overrun > 0, overrun)
        return PlanningResult(selected, fallback, stats, tuple(proposals))

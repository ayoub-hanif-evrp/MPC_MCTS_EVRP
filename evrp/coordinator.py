"""Exact minimum-cost compatible selection of FIRST actions only."""

from math import isfinite

from .mpc import CandidatePlan


def coordinate(candidates: dict[int, tuple[CandidatePlan, ...]],
               committed: frozenset[str] = frozenset()) -> dict[int, CandidatePlan]:
    """Solve rectangular assignment by min-cost flow with private fallback columns.

    Customers are shared columns; charge/wait/return alternatives share one private
    column per EV. Predicted second and later customer visits create no conflicts.
    Successive shortest augmenting paths use Bellman-Ford (negative costs allowed).
    """
    if not candidates:
        return {}
    ids = sorted(candidates)
    customers = sorted({p.first.destination for plans in candidates.values() for p in plans
                        if p.first.kind == "serve" and p.first.destination not in committed})
    columns = [("customer", c) for c in customers] + [("fallback", i) for i in ids]
    source = 0
    row_offset, col_offset = 1, 1 + len(ids)
    sink = col_offset + len(columns)
    graph: list[list[list]] = [[] for _ in range(sink + 1)]

    def add_edge(a: int, b: int, cost: float) -> list:
        forward = [b, len(graph[b]), 1, cost]
        backward = [a, len(graph[a]), 0, -cost]
        graph[a].append(forward)
        graph[b].append(backward)
        return forward

    records = []
    column_indices = {key: col_offset + j for j, key in enumerate(columns)}
    for i, vehicle_id in enumerate(ids):
        row = row_offset + i
        add_edge(source, row, 0.0)
        alternatives = {}
        for plan in candidates[vehicle_id]:
            if not plan.actions or not isfinite(plan.cost):
                raise ValueError("Coordinator requires nonempty finite-cost candidates")
            action = plan.first
            if action.kind == "serve" and action.destination in committed:
                continue
            key = ("customer", action.destination) if action.kind == "serve" else ("fallback", vehicle_id)
            if key not in alternatives or plan.cost < alternatives[key].cost:
                alternatives[key] = plan
        for key, plan in alternatives.items():
            edge = add_edge(row, column_indices[key], plan.cost)
            records.append((vehicle_id, plan, edge))
    for column in column_indices.values():
        add_edge(column, sink, 0.0)
    for _ in ids:
        distances = [float("inf")] * len(graph)
        previous = [None] * len(graph)
        distances[source] = 0.0
        for _ in range(len(graph) - 1):
            changed = False
            for a, edges in enumerate(graph):
                for j, (b, _, capacity, cost) in enumerate(edges):
                    if capacity and distances[a] + cost < distances[b]:
                        distances[b] = distances[a] + cost
                        previous[b] = (a, j)
                        changed = True
            if not changed:
                break
        if previous[sink] is None:
            raise ValueError("Candidate sets have no compatible first-action assignment")
        node = sink
        while node != source:
            a, j = previous[node]
            edge = graph[a][j]
            edge[2] -= 1
            graph[node][edge[1]][2] += 1
            node = a
    selected = {vehicle: plan for vehicle, plan, edge in records if edge[2] == 0}
    if len(selected) != len(ids):
        raise RuntimeError("Assignment did not select exactly one plan per vehicle")
    return selected

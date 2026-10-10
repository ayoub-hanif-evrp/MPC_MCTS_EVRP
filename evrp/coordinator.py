"""Three sequential MILPs: union coverage, new activations, predicted distance."""

from math import isfinite

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from .mpc import MPCProposal, action_key


def coordinate(candidates: dict[int, tuple[MPCProposal, ...]],
               committed: frozenset[str] = frozenset(), *,
               available: frozenset[str], background_intents=frozenset(),
               exclusive_routes=True) -> dict[int, MPCProposal]:
    if not candidates:
        return {}
    available = available - committed
    if not background_intents <= available:
        raise ValueError("Background intentions must be currently available")
    records = []
    for vehicle in sorted(candidates):
        for proposal in sorted(candidates[vehicle], key=lambda p: tuple(action_key(a) for a in p.actions)):
            if not proposal.actions or not isfinite(proposal.cost) or proposal.cost < 0:
                raise ValueError("Coordinator requires nonempty, nonnegative finite-distance proposals")
            if proposal.first.kind == "serve" and proposal.first.destination in committed:
                continue
            if not set(proposal.unique_predicted_customer_set) <= available:
                raise ValueError("Proposal contains unavailable or hidden customer information")
            records.append((vehicle, proposal))
    customer_ids = sorted(available)
    m, size = len(records), len(records) + len(customer_ids)
    if not records:
        raise ValueError("No admissible proposals")
    rows, lower, upper = [], [], []

    def constraint(values, lo, hi):
        rows.append(values)
        lower.append(lo)
        upper.append(hi)

    for vehicle in sorted(candidates):
        constraint({j: 1 for j, (k, _) in enumerate(records) if k == vehicle}, 1, 1)
    for offset, customer in enumerate(customer_ids):
        firsts = {j: 1 for j, (_, p) in enumerate(records) if p.first.kind == "serve" and p.first.destination == customer}
        constraint(firsts, 0, 1)
        covering = [j for j, (_, p) in enumerate(records) if customer in p.unique_predicted_customer_set]
        if exclusive_routes:
            constraint({j: 1 for j in covering}, 0, int(customer not in background_intents))
        z = m + offset
        constraint({z: 1, **{j: -1 for j in covering}}, -np.inf, int(customer in background_intents))
        if customer in background_intents:
            constraint({z: 1}, 1, 1)
        # Both directions make z the union indicator in every optimization stage.
        for j in covering:
            constraint({j: 1, z: -1}, -np.inf, 0)

    def solve(objective):
        matrix = lil_matrix((len(rows), size), dtype=float)
        for i, row in enumerate(rows):
            for j, value in row.items():
                matrix[i, j] = value
        result = milp(np.asarray(objective, dtype=float), integrality=np.ones(size), bounds=Bounds(0, 1),
                      constraints=LinearConstraint(matrix.tocsc(), lower, upper), options={"mip_rel_gap": 0.0})
        if not result.success or result.x is None:
            raise RuntimeError(f"Lexicographic coordination failed: {result.message}")
        solution = np.rint(result.x).astype(int)
        actual = matrix.tocsr() @ solution
        if np.any(actual < np.asarray(lower) - 1e-7) or np.any(actual > np.asarray(upper) + 1e-7):
            raise RuntimeError("MILP returned a numerically infeasible assignment")
        return solution

    solution = solve([0] * m + [-1] * len(customer_ids))
    coverage = int(solution[m:].sum())
    constraint({m + j: 1 for j in range(len(customer_ids))}, coverage, coverage)
    activation = [int(p.new_activation) for _, p in records] + [0] * len(customer_ids)
    solution = solve(activation)
    count = int(np.dot(activation, solution))
    constraint({j: a for j, a in enumerate(activation) if a}, count, count)
    solution = solve([p.total_predicted_distance for _, p in records] + [0] * len(customer_ids))
    selected = {k: p for j, (k, p) in enumerate(records) if solution[j]}
    if len(selected) != len(candidates):
        raise RuntimeError("Exactly one proposal per ready EV was not selected")
    return selected

from dataclasses import replace
import itertools
import random

import pytest

from evrp.coordinator import coordinate
from evrp.model import Action
from evrp.mpc import MPCProposal, proposal_key
from tests.test_planning import problem


def plan(first, *tail, active=False, distance=10):
    return MPCProposal((first,) + tuple(Action("serve", c) for c in tail), distance, new_activation=active)


WAIT = plan(Action("wait", wait_duration=1), distance=0)


def test_charge_first_service_dominates_wait():
    p = plan(Action("charge", "S", 10), "A", "B", active=True)
    assert proposal_key(p) < proposal_key(WAIT)
    assert coordinate({0: (p, WAIT)}, available=frozenset({"A", "B"}))[0] == p


def test_active_vehicle_covers_work_unused_vehicle_waits():
    serving = plan(Action("serve", "A"), "B")
    new = plan(Action("serve", "B"), active=True, distance=1)
    chosen = coordinate({0: (serving, WAIT), 1: (new, WAIT)}, available=frozenset({"A", "B"}))
    assert chosen == {0: serving, 1: WAIT}


def test_extra_service_dominates_activation_and_distance():
    a = plan(Action("serve", "A"), distance=1)
    b = plan(Action("serve", "B"), active=True, distance=1000000)
    chosen = coordinate({0: (a, WAIT), 1: (b, WAIT)}, available=frozenset({"A", "B"}))
    assert chosen[1] == b


def test_overlapping_future_tail_is_rejected_even_when_cheaper():
    a = plan(Action("serve", "A"), "C")
    b = plan(Action("serve", "B"), "C")
    d = plan(Action("serve", "D"), distance=50)
    chosen = coordinate({0: (a,), 1: (b, d)}, available=frozenset("ABCD"))
    assert chosen[1] == d


def test_hidden_intent_rejected():
    hidden = plan(Action("charge", "S", 10), "SECRET")
    with pytest.raises(ValueError, match="hidden"):
        coordinate({0: (hidden, WAIT)}, available=frozenset({"A"}))


def test_reward_bounded_and_one_service_dominates():
    p = problem()
    bound = p.observation.infrastructure.parameters.speed * p.observation.infrastructure.depot.due
    far = plan(Action("serve", "A"), distance=bound)
    near = plan(Action("wait", wait_duration=1), distance=0)
    assert p.reward(far) == 0.5 > p.reward(near)
    assert p.reward(replace(far, cost=0)) == 1.0


@pytest.mark.parametrize("seed", range(12))
def test_milp_matches_exhaustive_tail_coverage(seed):
    rng = random.Random(seed)
    options = {}
    for k in range(3):
        proposals = []
        for _ in range(3):
            sequence = rng.sample(list("ABCDE"), rng.randint(1, 3))
            first = Action("charge", "S", 10) if rng.random() < 0.4 else Action("serve", sequence.pop(0))
            proposals.append(plan(first, *sequence, active=bool(k % 2), distance=rng.uniform(1, 100)))
        options[k] = tuple(proposals) + (WAIT,)
    def score(joint):
        return (-len(set().union(*(set(p.unique_predicted_customer_set) for p in joint))),
                sum(p.new_activation for p in joint), sum(p.cost for p in joint))
    valid = []
    for joint in itertools.product(*options.values()):
        customers = [c for p in joint for c in p.unique_predicted_customer_set]
        if len(customers) == len(set(customers)):
            valid.append(score(joint))
    selected = coordinate(options, available=frozenset("ABCDE"))
    assert score(selected.values()) == pytest.approx(min(valid))

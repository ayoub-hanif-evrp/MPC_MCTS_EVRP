from dataclasses import replace
import itertools
import random

import pytest

from evrp.coordinator import coordinate
from evrp.model import Action, Observation, transition
from evrp.mpc import MPCConfig, MPCPlanningProblem, MPCProposal
from evrp.instance import Infrastructure, Location, Parameters
from evrp.model import VehicleState


def test_positive_sub_tolerance_wait():
    depot = Location("D", "d", 0, 0, 0, 0, 100, 0)
    infra = Infrastructure(depot, (), Parameters(10, 10, 1, 1, 1))
    state = VehicleState(0, depot, 10, 10, 10)
    step = transition(state, Action("wait", wait_duration=1e-12), Observation(10, infra, ()))
    assert step.after.time > state.time


def test_distance_only_free_wait_degeneracy_is_explicit():
    depot = Location("D", "d", 0, 0, 0, 0, 100, 0)
    customer = Location("C", "c", 1, 0, 1, 0, 90, 0)
    infra = Infrastructure(depot, (), Parameters(10, 10, 1, 1, 1))
    state = VehicleState(0, depot, 0, 10, 10)
    p = MPCPlanningProblem(Observation(0, infra, (customer,)), state, MPCConfig())
    serving = p.proposal((Action("serve", "C"),))
    idle = p.proposal((p.fallback(p.initial),))
    assert serving.cost == 2
    assert idle.cost == 0
    assert coordinate({0: (serving, idle)})[0].first.kind == "wait"


@pytest.mark.parametrize("seed", range(10))
def test_assignment_matches_exhaustive_enumeration(seed):
    rng = random.Random(seed)
    candidates = {}
    for k in range(4):
        candidates[k] = tuple(MPCProposal((Action("serve", c),), rng.uniform(-20, 20)) for c in ("A", "B")) + (
            MPCProposal((Action("wait", wait_duration=1),), rng.uniform(-20, 20)),)
    selected = coordinate(candidates)
    best = float("inf")
    for joint in itertools.product(*candidates.values()):
        customers = [p.first.destination for p in joint if p.first.kind == "serve"]
        if len(customers) == len(set(customers)):
            best = min(best, sum(p.cost for p in joint))
    assert sum(p.cost for p in selected.values()) == pytest.approx(best)

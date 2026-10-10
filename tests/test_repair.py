from collections import Counter
from dataclasses import replace
from math import isfinite, isinf

import pytest

from evrp import repair
from evrp.instance import Infrastructure, Location, Parameters
from evrp.model import Action, Observation, VehicleState, transition
from evrp.mpc import MPCConfig
from evrp.repair import build_route, regret_repair, route_proposal


def customer(name, x, due=100, ready=0, demand=1, service=0):
    return Location(name, "c", x, 0, demand, ready, due, service)


def setup(customers, *, stations=(), battery=100, capacity=10, charge_rate=1, horizon=5):
    depot = Location("D", "d", 0, 0, 0, 0, 200, 0)
    infra = Infrastructure(depot, stations, Parameters(battery, capacity, 1, charge_rate, 1))
    obs = Observation(0, infra, tuple(customers))
    state = VehicleState(0, depot, 0, battery, capacity)
    return state, obs, MPCConfig(prediction_horizon=horizon)


def serves(*ids):
    return tuple(Action("serve", c) for c in ids)


def claims(routes):
    return [a.destination for actions in routes.values() for a in actions if a.kind == "serve"]


def test_unique_option_precedes_multiple_options_and_preserves_inputs():
    state, obs, config = setup((customer("A", -1, due=2), customer("B", 1, due=20)), capacity=1)
    far = replace(state, id=1, location=replace(obs.infrastructure.depot, x=10), departed=True)
    origins, routes = {0: state, 1: far}, {0: (), 1: ()}
    updated, records = regret_repair(origins, routes, obs, config)
    assert [r["customer"] for r in records] == ["A", "B"]
    assert records[0]["feasible_options"] == 1
    assert records[0]["regret2"] is None
    assert updated == {0: serves("A"), 1: serves("B")}
    assert routes == {0: (), 1: ()}
    assert origins == {0: state, 1: far}


def test_actual_regret_order_overrides_due_date_and_uses_cheapest_vehicle():
    state, obs, config = setup((customer("A", 1, due=20), customer("B", 9)), capacity=1)
    far = replace(state, id=1, location=replace(obs.infrastructure.depot, x=10), departed=True)
    updated, records = regret_repair({0: state, 1: far}, {}, obs, config)
    # B costs 0 extra from vehicle 1 (already 10 from home), 18 from vehicle 0.
    # A's two insertion costs are 0 and 2, despite its earlier deadline.
    assert records[0]["customer"] == "B"
    assert records[0]["regret2"] == pytest.approx(18)
    assert records[0]["incremental_cost"] == pytest.approx(0)
    assert records[0]["feasible_options"] == 2
    assert updated == {0: serves("A"), 1: serves("B")}


@pytest.mark.parametrize("customers,first", [
    ((customer("A", 1, due=10), customer("B", 5, due=12)), "B"),
    ((customer("A", 1, due=10), customer("B", 3, due=12)), "A"),
    ((customer("B", 1, due=10), customer("A", 1, due=10)), "A"),
])
def test_equal_regret_ties_use_remaining_slack_then_due_then_id(customers, first):
    state, obs, config = setup(customers, capacity=1)
    _, records = regret_repair({0: state, 1: replace(state, id=1)}, {}, obs, config)
    assert records[0]["regret2"] == 0
    assert records[0]["customer"] == first


def test_positions_in_one_route_are_distinct_regret_options():
    state, obs, config = setup((customer("owned", 5), customer("new", 1)))
    updated, records = regret_repair({0: state}, {0: serves("owned")}, obs, config)
    assert records[0]["feasible_options"] == 2
    assert records[0]["regret2"] == 0
    assert records[0]["position"] == 0
    assert updated[0] == serves("new", "owned")


def test_cheapest_feasible_position_preserves_all_old_customers():
    state, obs, config = setup((customer("early", 1, due=2), customer("far", 4),
                                customer("new", 3)))
    original = serves("early", "far")
    updated, records = regret_repair({0: state}, {0: original}, obs, config)
    assert updated[0] == serves("early", "new", "far")
    assert records[0]["position"] == 1
    assert records[0]["feasible_options"] == 2
    assert records[0]["incremental_cost"] == pytest.approx(0)
    assert route_proposal(state, updated[0], obs, config).cost == pytest.approx(8)


@pytest.mark.parametrize("job,battery,capacity", [
    (customer("bad", 6), 5, 10),
    (customer("bad", 4), 5, 10),  # Can reach, cannot return safely.
    (customer("bad", 5, due=4), 100, 10),
    (customer("bad", 1, demand=2), 100, 1),
    (customer("bad", 1, ready=199, due=200, service=2), 100, 10),
])
def test_infeasible_battery_time_capacity_and_return_rejected(job, battery, capacity):
    state, obs, config = setup((job,), battery=battery, capacity=capacity)
    assert build_route(state, (job.id,), obs, config) is None
    assert route_proposal(state, serves(job.id), obs, config) is None
    assert regret_repair({0: state}, {}, obs, config) == ({0: ()}, [])


def test_hidden_committed_and_duplicate_services_never_enter_proposals():
    state, obs, config = setup((customer("A", 1), customer("busy", 2)))
    obs = replace(obs, committed_customers=(("busy", 1),))
    for sequence in (("hidden",), ("busy",), ("A", "A")):
        assert build_route(state, sequence, obs, config) is None
        assert route_proposal(state, serves(*sequence), obs, config) is None
    updated, records = regret_repair({0: state}, {}, obs, config)
    assert claims(updated) == ["A"]
    assert [r["customer"] for r in records] == ["A"]


def test_owned_and_previously_served_customers_are_excluded():
    state, obs, config = setup((customer("A", 1), customer("B", 2), customer("C", 3)))
    state = replace(state, served_customers=("C",), departed=True)
    updated, records = regret_repair({0: state, 1: replace(state, id=1)}, {0: serves("A")}, obs, config)
    assert sorted(claims(updated)) == ["A", "B"]
    assert [r["customer"] for r in records] == ["B"]
    assert "A" in claims({0: updated[0]})


def test_duplicate_ownership_is_an_explicit_input_error():
    state, obs, config = setup((customer("A", 1),))
    with pytest.raises(ValueError, match="Duplicate"):
        regret_repair({0: state, 1: replace(state, id=1)}, {0: serves("A"), 1: serves("A")}, obs, config)


def test_invalid_fleet_and_hidden_input_routes_are_explicit_errors():
    state, obs, config = setup((customer("A", 1),))
    with pytest.raises(ValueError, match="fixed fleet"):
        regret_repair({0: state}, {9: ()}, obs, config)
    with pytest.raises(ValueError, match="never be finished"):
        regret_repair({0: replace(state, finished=True)}, {}, obs, config)
    with pytest.raises(ValueError, match="hidden or committed"):
        regret_repair({0: state}, {0: serves("hidden")}, obs, config)
    with pytest.raises(ValueError, match="last service"):
        regret_repair({0: state}, {0: serves("A") + (Action("return", "D"),)}, obs, config)


def test_fixed_unused_fleet_and_activation_only_after_dispatch():
    state, obs, config = setup(tuple(customer(str(i), i + 1) for i in range(3)), capacity=1)
    origins = {7: replace(state, id=7), 12: replace(state, id=12)}
    updated, records = regret_repair(origins, {}, obs, config)
    assert set(updated) == {7, 12}
    assert len(records) == len(claims(updated)) == 2
    assert all(not s.departed for s in origins.values())
    assert all(r["new_activation"] for r in records)
    for k, actions in updated.items():
        assert transition(origins[k], actions[0], obs).after.departed


def test_activation_is_only_a_distance_tie_break():
    state, obs, config = setup((customer("A", 1),))
    active = replace(state, id=9, departed=True)
    updated, records = regret_repair({0: state, 9: active}, {}, obs, config)
    assert updated[0] == ()
    assert records[0]["vehicle_id"] == 9
    assert not records[0]["new_activation"]
    # A low-battery active EV needing a charging detour is more expensive.
    station = Location("S", "f", 0, 4, 0, 0, 200, 0)
    state, obs, config = setup((customer("A", 4),), stations=(station,), battery=10)
    active = replace(state, id=9, battery=4, departed=True)
    _, records = regret_repair({0: state, 9: active}, {}, obs, config)
    assert records[0]["vehicle_id"] == 0


@pytest.mark.parametrize("horizon", [1, 3, 5])
def test_full_suffix_and_insertions_are_not_limited_by_mpc_horizon(horizon):
    state, obs, config = setup(tuple(customer(str(i), i) for i in range(1, 9)), horizon=horizon)
    original = serves(*(str(i) for i in range(1, 8)))
    proposal = route_proposal(state, original, obs, config)
    assert proposal is not None
    assert proposal.predicted_service_count == 7
    assert proposal.cost == pytest.approx(14)
    updated, records = regret_repair({0: state}, {0: original}, obs, config)
    assert len(records) == 1
    assert len(claims(updated)) == 8
    assert tuple(c for c in claims(updated) if c != "8") == tuple(str(i) for i in range(1, 8))
    assert route_proposal(state, updated[0], obs, config).cost == pytest.approx(16)
    assert config.prediction_horizon == horizon


def test_busy_origin_starts_after_immutable_action_and_sees_only_current_release():
    state, obs, config = setup((customer("busy", 5, service=20), customer("new", 6),
                                customer("too_late", 1, due=10)))
    immutable = transition(state, Action("serve", "busy"), obs)
    obs = replace(obs, time=5, committed_customers=(("busy", 0),))
    updated, records = regret_repair({0: immutable.after}, {}, obs, config)
    assert claims(updated) == ["new"]
    assert records[0]["customer"] == "new"
    result = route_proposal(immutable.after, updated[0], obs, config)
    assert result.predicted_end_state.time == 26
    assert immutable.after.time == 25
    assert immutable.action == Action("serve", "busy")


def test_stale_or_invalid_origins_cannot_insert_even_into_empty_routes():
    state, obs, config = setup((customer("A", 1),))
    stale = replace(obs, time=1)
    assert regret_repair({0: state}, {}, stale, config) == ({0: ()}, [])
    assert build_route(state, (), stale, config) is None
    assert route_proposal(state, serves("A"), stale, config) is None
    for invalid in (replace(state, battery=float("nan")), replace(state, load=-1),
                    replace(state, current_committed_action=Action("serve", "A"))):
        assert regret_repair({0: invalid}, {}, obs, config) == ({0: ()}, [])


def test_partial_bridge_meets_window_that_full_charge_misses():
    station = Location("S", "f", 4, 0, 0, 0, 200, 0)
    state, obs, config = setup((customer("A", 6, due=10),), stations=(station,), battery=10)
    state = replace(state, battery=6)
    assert route_proposal(state, serves("A"), obs, config) is None
    actions = build_route(state, ("A",), obs, config)
    assert actions == (Action("charge", "S", 4), Action("serve", "A"))
    result = route_proposal(state, actions, obs, config)
    assert result.cost == pytest.approx(12)
    assert result.terminal_return_distance == pytest.approx(6)
    assert result.charging_time == pytest.approx(2)
    full = replace(config, charging_mode="full")
    assert build_route(state, ("A",), obs, full) is None
    assert route_proposal(state, actions, obs, full) is None


@pytest.mark.parametrize("mode", ["partial", "full"])
def test_multihop_full_charge_fallback_and_safe_return(mode):
    stations = tuple(Location(name, "f", x, 0, 0, 0, 200, 0) for name, x in (("S1", 3), ("S2", 8)))
    state, obs, config = setup((customer("A", 10),), stations=stations, battery=6)
    config = replace(config, charging_mode=mode)
    actions = build_route(state, ("A",), obs, config)
    assert actions == (Action("charge", "S1", 6), Action("charge", "S2", 6), Action("serve", "A"))
    result = route_proposal(state, actions, obs, config)
    assert result is not None and isfinite(result.cost)
    assert result.cost == pytest.approx(20)
    assert result.predicted_charging_actions == 2
    assert actions[-1].kind == "serve"


def test_direct_travel_is_preferred_and_empty_route_semantics():
    station = Location("S", "f", 1, 0, 0, 0, 200, 0)
    state, obs, config = setup((customer("A", 2),), stations=(station,))
    assert build_route(state, ("A",), obs, config) == serves("A")
    assert build_route(state, (), obs, config) == ()
    assert route_proposal(state, (), obs, config) is None


def test_original_charging_route_is_retained_when_insertion_fails():
    station = Location("S", "f", 4, 0, 0, 0, 200, 0)
    state, obs, config = setup((customer("owned", 6), customer("bad", 2, demand=2)),
                               stations=(station,), battery=10, capacity=1)
    state = replace(state, battery=6)
    original = (Action("charge", "S", 8), Action("serve", "owned"))
    assert route_proposal(state, original, obs, config) is not None
    assert regret_repair({0: state}, {0: original}, obs, config) == ({0: original}, [])


def test_repair_can_rebuild_charging_without_losing_owned_sequence():
    station = Location("S", "f", 4, 0, 0, 0, 200, 0)
    state, obs, config = setup((customer("owned", 1), customer("new", 6, ready=4, due=12)),
                               stations=(station,), battery=10)
    state = replace(state, battery=6)
    updated, records = regret_repair({0: state}, {0: serves("owned")}, obs, config)
    assert len(records) == 1
    assert sorted(claims(updated)) == ["new", "owned"]
    assert any(a.kind == "charge" for a in updated[0])
    assert route_proposal(state, updated[0], obs, config) is not None


def test_unchanged_owner_options_are_cached_across_insertions(monkeypatch):
    state, obs, config = setup((customer("A", -1, due=2), customer("B", 1, due=20)), capacity=1)
    far = replace(state, id=1, location=replace(obs.infrastructure.depot, x=10), departed=True)
    original, calls = repair.build_route, Counter()

    def counted(state, sequence, observation, config):
        calls[(state.id, sequence)] += 1
        return original(state, sequence, observation, config)

    monkeypatch.setattr(repair, "build_route", counted)
    _, records = regret_repair({0: state, 1: far}, {}, obs, config)
    assert [r["customer"] for r in records] == ["A", "B"]
    assert calls[(1, ("B",))] == 1
    assert calls[(0, ("A", "B"))] == 1
    assert calls[(0, ("B", "A"))] == 1


def test_deterministic_finite_termination_with_infeasible_leftovers():
    state, obs, config = setup(tuple(customer(str(i), i + 1) for i in range(5))
                               + (customer("impossible", 150),), capacity=2)
    origins = {4: replace(state, id=4), 1: replace(state, id=1)}
    first = regret_repair(origins, {}, obs, config)
    assert first == regret_repair(dict(reversed(tuple(origins.items()))), {},
                                  replace(obs, customers=tuple(reversed(obs.customers))), config)
    updated, records = first
    assert len(records) == 4 <= len(obs.customers)
    assert len(claims(updated)) == len(set(claims(updated)))
    assert "impossible" not in claims(updated)
    assert regret_repair(origins, updated, obs, config) == (updated, [])

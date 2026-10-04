"""Offline feasibility control, never an online routing competitor."""

from .model import EPS, Observation, transition
from .reference import initial_vehicle, validate_reference


def oracle_reference(instance, reference, scenario, config):
    from .experiments import static_reference_result

    validate_reference(instance, reference)
    if scenario.reference_schedule_identifier != reference.identifier:
        raise ValueError("Oracle must replay the scenario's own reference")
    releases = dict(scenario.customer_release_times)
    steps, served = [], set()
    for k, route in enumerate(reference.routes):
        state = initial_vehicle(instance, k)
        for stored in route.steps:
            visible = tuple(c for c in instance.customers if releases[c.id] <= state.time)
            if stored.served and releases[stored.served] > state.time + EPS:
                raise ValueError("Reference dispatch precedes customer release")
            actual = transition(state, stored.action, Observation(state.time, instance.infrastructure, visible))
            if actual != stored:
                raise ValueError("Oracle physical replay differs from reference")
            if actual.served:
                if actual.served in served:
                    raise ValueError("Duplicate oracle service")
                served.add(actual.served)
            steps.append(actual)
            state = actual.after
        if not state.finished or state.location != instance.infrastructure.depot:
            raise ValueError("Oracle did not return safely")
    if served != {c.id for c in instance.customers}:
        raise ValueError("Oracle failed complete service; stop online diagnostics")
    result = static_reference_result(instance, reference, scenario, config)
    result.steps = steps
    result.metadata.update(algorithm="ORACLE_REFERENCE", policy_role="offline feasibility oracle",
                           offline_reference_not_online_baseline=True)
    result.effective_config["algorithm"] = "ORACLE_REFERENCE"
    return result

from dataclasses import asdict, replace

from evrp.instance import load_instance
from evrp.observation import get_agent_observation, initial_global_state
from evrp.reference import ReferenceConfig, solve_reference
from evrp.scenario import generate
from evrp.storage import BENCHMARK


def test_observation_boundary():
    instance = load_instance(BENCHMARK / "c101C5.txt")
    reference = solve_reference(instance, ReferenceConfig(multistarts=1))
    scenario = generate(instance, reference, 9, 1)
    state = initial_global_state(instance, scenario)
    initial = state.reveal()
    state.check_partition(instance)
    observation = get_agent_observation(state, instance)
    assert {c.id for c in observation.customers} == set(initial)
    assert set(state.hidden_customers).isdisjoint(c.id for c in observation.customers)
    assert set(asdict(observation)) == {"time", "infrastructure", "customers", "committed_customers"}
    key, (_, release) = min(state.hidden_customers.items(), key=lambda item: item[1][1])
    state.time = release - 1e-9
    state.reveal()
    assert key not in {c.id for c in get_agent_observation(state, instance).customers}
    state.time = release
    assert key in state.reveal()
    assert key in {c.id for c in get_agent_observation(state, instance).customers}


def test_hidden_attributes_cannot_change_current_observation():
    instance = load_instance(BENCHMARK / "c101C5.txt")
    reference = solve_reference(instance, ReferenceConfig(multistarts=1))
    state = initial_global_state(instance, generate(instance, reference, 1, 1))
    state.reveal()
    first = get_agent_observation(state, instance)
    for key, (customer, release) in list(state.hidden_customers.items()):
        state.hidden_customers[key] = (replace(customer, x=9999, demand=9999), release + 9000)
    assert get_agent_observation(state, instance) == first

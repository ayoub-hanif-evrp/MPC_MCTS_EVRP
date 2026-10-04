"""Simulator-private global state and the sole policy-facing observation boundary."""

from dataclasses import dataclass, field

from .instance import Instance, Location
from .model import Observation, Transition, VehicleState
from .scenario import DynamicScenario


@dataclass
class GlobalState:
    time: float
    vehicles: dict[int, VehicleState]
    hidden_customers: dict[str, tuple[Location, float]]
    available_customers: dict[str, Location] = field(default_factory=dict)
    committed_customers: dict[str, int] = field(default_factory=dict)
    served_customers: set[str] = field(default_factory=set)
    busy: dict[int, Transition] = field(default_factory=dict)
    idle_until: dict[int, float] = field(default_factory=dict)

    def reveal(self) -> tuple[str, ...]:
        revealed = tuple(sorted(key for key, (_, release) in self.hidden_customers.items() if release <= self.time))
        for key in revealed:
            customer, _ = self.hidden_customers.pop(key)
            self.available_customers[key] = customer
        return revealed

    def check_partition(self, instance: Instance) -> None:
        partitions = [set(self.hidden_customers), set(self.available_customers),
                      set(self.committed_customers), self.served_customers]
        assert sum(map(len, partitions)) == len(set.union(*partitions))
        assert set.union(*partitions) == {c.id for c in instance.customers}


def get_agent_observation(state: GlobalState, instance: Instance) -> Observation:
    # No Instance, scenario, release calendar, or hidden-customer counts cross this boundary.
    return Observation(state.time, instance.infrastructure,
                       tuple(state.available_customers[key] for key in sorted(state.available_customers)),
                       tuple(sorted(state.committed_customers.items())))


def initial_global_state(instance: Instance, scenario: DynamicScenario) -> GlobalState:
    from .reference import initial_vehicle

    scenario.validate(instance)
    releases = dict(scenario.customer_release_times)
    return GlobalState(instance.infrastructure.depot.ready,
                       {k: initial_vehicle(instance, k) for k in range(scenario.fleet_size)},
                       {c.id: (c, releases[c.id]) for c in instance.customers})

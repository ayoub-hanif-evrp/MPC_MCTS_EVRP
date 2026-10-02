"""Reference-schedule-preserving dynamicization inspired by Yang et al."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import json
import random

from .instance import Instance
from .reference import ReferenceSchedule, validate_reference
from .storage import identifier, save_json

METHOD = "reference-schedule-preserving dynamicization inspired by Yang et al."


@dataclass(frozen=True)
class DynamicScenario:
    base_instance: str
    instance_sha256: str
    scenario_method: str
    selection_mode: str
    target_DoD: float
    realized_DoD: float
    scenario_seed: int
    reference_schedule_identifier: str
    fleet_size: int
    customer_release_times: tuple[tuple[str, float], ...]
    release_upper_bounds: tuple[tuple[str, float], ...]
    eligible_count: int
    requested_dynamic_count: int
    schema_version: int = 1

    @property
    def identifier(self) -> str:
        return identifier(self)

    def validate(self, instance: Instance) -> None:
        if self.schema_version != 1 or self.scenario_method != METHOD:
            raise ValueError("Unsupported scenario schema or method")
        if (self.base_instance, self.instance_sha256) != (instance.name, instance.sha256):
            raise ValueError("Scenario benchmark name/SHA-256 mismatch")
        if self.selection_mode not in {"bernoulli", "exact_count"} or not 0 <= self.target_DoD <= 1:
            raise ValueError("Invalid selection policy")
        releases, bounds = dict(self.customer_release_times), dict(self.release_upper_bounds)
        ids = {c.id for c in instance.customers}
        if (set(releases) != ids or len(releases) != len(self.customer_release_times)
                or set(bounds) != ids or len(bounds) != len(self.release_upper_bounds)):
            raise ValueError("Each customer must have exactly one release and bound")
        for c in instance.customers:
            release, upper = releases[c.id], bounds[c.id]
            if not isfinite(release) or not isfinite(upper) or not 0 <= release <= upper <= c.ready:
                raise ValueError("Release violates its reference-derived upper bound")
        realized = sum(t > 0 for t in releases.values()) / len(ids) if ids else 0.0
        if (not isfinite(self.realized_DoD) or abs(realized - self.realized_DoD) > 1e-12
                or type(self.fleet_size) is not int or self.fleet_size < 1):
            raise ValueError("Inconsistent realized dynamicity or fleet size")
        if self.eligible_count != sum(t > 0 for t in bounds.values()):
            raise ValueError("Inconsistent eligibility metadata")

    def save(self, path: str | Path) -> None:
        save_json(path, self)

    @classmethod
    def load(cls, path: str | Path, instance: Instance) -> "DynamicScenario":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for key in ("customer_release_times", "release_upper_bounds"):
            data[key] = tuple((str(name), float(value)) for name, value in data[key])
        scenario = cls(**data)
        scenario.validate(instance)
        return scenario


def generate(instance: Instance, reference: ReferenceSchedule, seed: int, dynamicity: float = 0.5,
             selection_mode: str = "exact_count") -> DynamicScenario:
    validate_reference(instance, reference)
    if not 0 <= dynamicity <= 1 or selection_mode not in {"bernoulli", "exact_count"}:
        raise ValueError("Invalid scenario generation settings")
    if instance.infrastructure.depot.ready != 0:
        raise ValueError("Dynamicization requires depot opening at time zero")
    rng = random.Random(seed)
    departures = reference.predecessor_departures
    bounds = {c.id: min(c.ready, departures[c.id]) for c in sorted(instance.customers, key=lambda c: c.id)}
    eligible = [key for key, upper in bounds.items() if upper > 0]
    # Half-up rounding is explicit, avoiding language-dependent ties-to-even behavior.
    requested = int(dynamicity * len(bounds) + 0.5)
    if selection_mode == "exact_count":
        chosen = set(rng.sample(eligible, min(requested, len(eligible))))
    else:
        draws = {key for key in bounds if rng.random() < dynamicity}
        chosen = draws.intersection(eligible)
        requested = len(draws)
    releases = tuple((key, (1.0 - rng.random()) * upper if key in chosen else 0.0)
                     for key, upper in bounds.items())
    result = DynamicScenario(instance.name, instance.sha256, METHOD, selection_mode, dynamicity,
                             len(chosen) / len(bounds) if bounds else 0.0, seed, reference.identifier,
                             reference.fleet_size, releases, tuple(bounds.items()), len(eligible), requested)
    result.validate(instance)
    return result


Scenario = DynamicScenario

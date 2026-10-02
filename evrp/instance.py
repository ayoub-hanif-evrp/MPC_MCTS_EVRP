"""Read-only Schneider benchmark parsing and immutable problem data."""

from dataclasses import dataclass
from hashlib import sha256
from math import hypot, isfinite
from pathlib import Path
import re


@dataclass(frozen=True)
class Location:
    id: str
    kind: str
    x: float
    y: float
    demand: float
    ready: float
    due: float
    service: float


@dataclass(frozen=True)
class Parameters:
    battery: float
    capacity: float
    consumption: float
    inverse_charge_rate: float
    speed: float


@dataclass(frozen=True)
class Infrastructure:
    depot: Location
    stations: tuple[Location, ...]
    parameters: Parameters


@dataclass(frozen=True)
class Instance:
    name: str
    sha256: str
    infrastructure: Infrastructure
    customers: tuple[Location, ...]


ProblemInstance = Instance


def distance(a: Location, b: Location) -> float:
    return hypot(a.x - b.x, a.y - b.y)


def load_instance(path: str | Path) -> Instance:
    path = Path(path)
    raw = path.read_bytes()
    rows: list[Location] = []
    params: dict[str, float] = {}
    for line in raw.decode("utf-8-sig").splitlines():
        fields = line.split()
        if not fields or fields[0] == "StringID":
            continue
        match = re.fullmatch(r"([QCrgv])\s+[^/]+/\s*([^/]+)\s*/", line.strip())
        if match:
            key, value = match.groups()
            if key in params:
                raise ValueError(f"Duplicate parameter {key}")
            params[key] = float(value)
            continue
        if len(fields) != 8 or fields[1] not in {"d", "f", "c"}:
            raise ValueError(f"Invalid Schneider row: {line!r}")
        row = Location(fields[0], fields[1], *(float(v) for v in fields[2:]))
        values = (row.x, row.y, row.demand, row.ready, row.due, row.service)
        if not all(isfinite(v) for v in values):
            raise ValueError("Non-finite location data")
        if min(row.demand, row.ready, row.service) < 0 or row.ready > row.due:
            raise ValueError(f"Invalid bounds at {row.id}")
        rows.append(row)
    if set(params) != set("QCrgv") or any(not isfinite(v) or v <= 0 for v in params.values()):
        raise ValueError("Five finite positive vehicle parameters are required")
    depots = [row for row in rows if row.kind == "d"]
    if len(depots) != 1 or len({r.id for r in rows}) != len(rows):
        raise ValueError("Exactly one depot and unique location IDs are required")
    depot = depots[0]
    stations = tuple(row for row in rows if row.kind == "f")
    # The return-path oracle relies on the common operating interval in Schneider.
    if any(s.ready != depot.ready or s.due != depot.due or s.service or s.demand for s in stations):
        raise ValueError("Stations must share depot hours and have zero demand/service")
    if depot.service or depot.demand:
        raise ValueError("Depot must have zero demand/service")
    parameters = Parameters(*(params[key] for key in "QCrgv"))
    return Instance(path.stem, sha256(raw).hexdigest(), Infrastructure(depot, stations, parameters),
                    tuple(row for row in rows if row.kind == "c"))

"""File-based research artifacts, with benchmark write protection."""

from dataclasses import asdict, is_dataclass
from hashlib import sha256
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "data" / "evrptw_instances"


def writable_path(path: str | Path) -> Path:
    path = Path(path)
    if path.resolve().is_relative_to(BENCHMARK.resolve()):
        raise ValueError("Original benchmark files are read-only")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def canonical(data: object) -> str:
    return json.dumps(asdict(data) if is_dataclass(data) else data,
                      sort_keys=True, separators=(",", ":"), allow_nan=False)


def identifier(data: object) -> str:
    return sha256(canonical(data).encode("utf-8")).hexdigest()


def save_json(path: str | Path, data: object) -> None:
    path = writable_path(path)
    encoded = json.dumps(asdict(data) if is_dataclass(data) else data,
                         indent=2, sort_keys=True, allow_nan=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def benchmark_hashes() -> dict[str, str]:
    return {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(BENCHMARK.glob("*.txt"))}

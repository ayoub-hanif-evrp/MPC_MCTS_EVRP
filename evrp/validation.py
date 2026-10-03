"""Published small-instance checks, metadata only; no benchmark download."""

from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .instance import load_instance
from .reference import ReferenceConfig, solve_reference
from .storage import BENCHMARK, writable_path
from .versions import REFERENCE_SOLVER_VERSION

SOURCE = "https://web4.ensiie.fr/~faye/mpro/MPRO_reseau/Projet_2020/The%20electric%20vehicle%20routing%20problem%20with%20time%20windows%20and%20recharging%20stations.pdf"
PUBLISHED = {"c101C5": (2, 257.75), "c103C5": (1, 176.05),
             "c206C5": (1, 242.56), "c208C5": (1, 158.48)}


def validate_references(output="results/summaries", config=ReferenceConfig()):
    rows = []
    for name, (vehicles, distance) in PUBLISHED.items():
        instance = load_instance(BENCHMARK / f"{name}.txt")
        reference = solve_reference(instance, config)
        match = vehicles == reference.fleet_size
        passed = match and abs(reference.total_distance - distance) <= 0.011
        rows.append(dict(instance=name, published_vehicles=vehicles,
                         our_vehicles=reference.fleet_size, vehicle_match=match,
                         published_distance=distance, our_distance=reference.total_distance,
                         distance_gap_percent=100 * (reference.total_distance / distance - 1),
                         validation_status="passed" if passed else "FAILED",
                         instance_sha256=instance.sha256, reference_hash=reference.identifier,
                         reference_solver_version=REFERENCE_SOLVER_VERSION,
                         config=str(asdict(config)), source=SOURCE, source_table="Table 3, CPLEX column"))
    frame = pd.DataFrame(rows)
    frame.to_csv(writable_path(Path(output) / "reference_validation.csv"), index=False)
    return frame


def require_reference_validation():
    frame = validate_references()
    if not frame.validation_status.eq("passed").all():
        raise RuntimeError("Reference validation failed; main study is blocked")

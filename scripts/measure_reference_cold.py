"""Recompute selected existing references; require exact content-hash equality."""

import os
for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import argparse
from pathlib import Path
from time import perf_counter

from evrp.experiments import prepare, source_fingerprint
from evrp.reference import solve_reference
from evrp.runtime import peak_memory_mib
from evrp.storage import save_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instances", nargs="+", default=["c101_21", "r201_21", "rc201_21"])
    args = parser.parse_args()
    rows = []
    source = source_fingerprint()
    for name in args.instances:
        instance, expected, _, _ = prepare(name, {})
        solve_reference.cache_clear()
        start = perf_counter()
        actual = solve_reference(instance, expected.config)
        seconds = perf_counter()-start
        assert actual.identifier == expected.identifier, "Exact reference caching changed the route trace"
        assert source_fingerprint() == source
        row = dict(instance=name, seconds=seconds, identical_reference=True,
                   reference_hash=actual.identifier, source_sha256=source, peak_memory_mib=peak_memory_mib())
        rows.append(row)
        save_json("results/performance/reference_cold.json", rows)
        print(row, flush=True)


if __name__ == "__main__":
    main()

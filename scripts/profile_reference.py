"""Measure repeated route-prefix work without changing the reference method."""

import argparse
import cProfile
from collections import OrderedDict
from pathlib import Path
from time import perf_counter

from evrp.experiments import prepare
from evrp.reference import evaluate_route
from evrp.storage import canonical, save_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--cache", action="store_true")
    args = parser.parse_args()
    instance, reference, _, _ = prepare("r201_21", {})
    sequence = reference.routes[0].customers
    cases = [sequence[:length] for length in range(20, len(sequence)+1)]
    cache = OrderedDict()
    profile = cProfile.Profile()
    started = perf_counter()
    profile.enable()
    results = [evaluate_route(instance, case, **({"prefix_cache": cache} if args.cache else {})) for case in cases]
    profile.disable()
    elapsed = perf_counter()-started
    import pstats
    stats = pstats.Stats(profile)
    calls = sum(value[1] for (file, _, name), value in stats.stats.items() if name == "transition" and file.endswith("model.py"))
    report = dict(seconds=elapsed, cases=len(cases), transition_calls=calls,
                  routes=[canonical(result) if result else None for result in results])
    save_json(Path("results/performance") / f"reference_{args.label}.json", report)
    print({k: v for k, v in report.items() if k != "routes"}, flush=True)


if __name__ == "__main__":
    main()

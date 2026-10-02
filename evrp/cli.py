"""Command-line entry points for file-based reproducible research."""

import argparse
import json
from pathlib import Path

from .experiments import load_config, prepare, run_grid, run_single


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("reference", "scenario", "run", "benchmark", "ablations", "smoke"):
        item = sub.add_parser(command)
        item.add_argument("--config", default=f"configs/{command if command in {'benchmark', 'ablations'} else 'debug'}.yaml")
        if command in {"reference", "scenario", "run"}:
            item.add_argument("--instance", default="c101C5")
        item.add_argument("--output", default="results/runs")
        item.add_argument("--algorithm")
        item.add_argument("--dynamicity", type=float)
        item.add_argument("--scenario-seed", type=int)
        item.add_argument("--scenario")
    for command in ("aggregate", "plot"):
        item = sub.add_parser(command)
        item.add_argument("--input", default="results/runs")
        item.add_argument("--output", default="results/aggregate" if command == "aggregate" else "results/figures")
    args = parser.parse_args(argv)
    if args.command in {"aggregate", "plot"}:
        if args.command == "aggregate":
            from .analysis import aggregate
            print(json.dumps(aggregate(args.input, args.output), indent=2))
        else:
            from .plotting import make_figures
            print(f"Created {len(make_figures(args.input, args.output))} figures in {args.output}")
        return
    config = load_config(args.config)
    for key in ("algorithm", "dynamicity", "scenario_seed"):
        if getattr(args, key) is not None:
            config[key] = getattr(args, key)
    if args.scenario:
        config["scenario_path"] = args.scenario
    if args.command in {"reference", "scenario"}:
        instance, reference, scenario, path = prepare(args.instance, config)
        print(json.dumps({"instance": instance.name, "reference": reference.identifier, "K": reference.fleet_size,
                          "reference_distance": reference.total_distance, "scenario": str(path),
                          "target_DoD": scenario.target_DoD, "realized_DoD": scenario.realized_DoD}, indent=2))
        return
    if args.command == "run":
        paths = [run_single(args.instance, config, args.output)]
    elif args.command == "smoke":
        cases = [("c101C5", 0.0), ("c101C5", 0.5), ("r104C5", 0.5), ("rc105C5", 0.5),
                 ("c101C10", 0.5), ("c103C15", 0.5), ("c101_21", 0.5)]
        def smoke_paths():
            for instance, dynamicity in cases:
                effective = {**config, "dynamicity": dynamicity}
                if instance.endswith("_21"):
                    effective.update(mcts_iterations=2, prediction_horizon=1, reference_solver_multistarts=1)
                yield run_single(instance, effective, args.output)
        paths = smoke_paths()
    else:
        paths = run_grid(config, args.output, args.command == "ablations")
    failed = 0
    for path in paths:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
        print(json.dumps({"path": str(path), "status": result["status"], "metrics": result["metrics"],
                          "error": result.get("error")}), flush=True)
        failed += result["status"] == "failed"
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

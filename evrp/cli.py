"""Command-line entry points for file-based reproducible research."""

import argparse
import json
from pathlib import Path

from .experiments import load_config, prepare, run_grid, run_single
from .storage import load_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("reference", "scenario", "run", "benchmark", "ablations", "smoke", "validate", "realtime"):
        item = sub.add_parser(command)
        item.add_argument("--config", default=f"configs/{command if command in {'ablations', 'realtime'} else 'pilot'}.yaml")
        if command in {"reference", "scenario", "run"}:
            item.add_argument("--instance", default="c101C5")
        item.add_argument("--output")
        item.add_argument("--algorithm")
        item.add_argument("--dynamicity", type=float)
        item.add_argument("--scenario-seed", type=int)
        item.add_argument("--scenario")
    for command in ("aggregate", "plot", "tables", "audit", "representative"):
        item = sub.add_parser(command)
        item.add_argument("--input", default="results/raw" if command in {"aggregate", "audit"} else "results/raw/pilot" if command == "representative" else "results/summaries")
        item.add_argument("--output", default="results/summaries" if command in {"aggregate", "audit"} else "results/tables" if command == "tables" else "results/figures/representative" if command == "representative" else "results/figures")
        item.add_argument("--study", default="pilot")
    args = parser.parse_args(argv)
    if args.command in {"aggregate", "plot", "tables", "audit", "representative"}:
        if args.command == "aggregate":
            from .analysis import aggregate
            print(json.dumps(aggregate(args.input, args.output), indent=2))
        elif args.command == "plot":
            from .plotting import make_figures
            print(f"Created {len(make_figures(args.input, args.output, args.study))} figures in {args.output}")
        elif args.command == "tables":
            from .analysis import export_tables
            print(f"Exported {len(export_tables(args.input, args.output))} CSV/LaTeX table pairs")
        elif args.command == "audit":
            from .audit import audit_directory
            frame = audit_directory(args.input, args.output)
            print(frame.to_string(index=False))
            if not frame.structural_valid.all():
                raise SystemExit(1)
        else:
            from .plotting import representative_figures
            print(f"Created {len(representative_figures(args.input, args.output))} representative figures")
        return
    config = load_config(args.config)
    if args.command == "validate":
        from .validation import validate_references
        from .reference import ReferenceConfig
        frame = validate_references(args.output or "results/summaries", ReferenceConfig(
            config.get("reference_solver_multistarts", 3), config.get("reference_improvement_passes", 1),
            config.get("reference_seed", 0), config.get("reference_label_limit", 24)))
        print(frame[["instance", "our_vehicles", "our_distance", "validation_status"]].to_string(index=False))
        if not frame.validation_status.eq("passed").all():
            raise SystemExit(1)
        return
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
                 ("c101C10", 0.5), ("c103C15", 0.5)]
        def smoke_paths():
            for instance, dynamicity in cases:
                effective = {k: v for k, v in config.items() if k not in {"grid", "instances"}}
                effective.update(dynamicity=dynamicity, study="pilot")
                yield run_single(instance, effective, args.output)
        paths = smoke_paths()
    else:
        paths = run_grid(config, args.output, args.command == "ablations")
    failed = 0
    for path in paths:
        result = load_json(path)
        print(json.dumps({"path": str(path), "status": result["status"], "metrics": result["metrics"],
                          "error": result.get("error")}), flush=True)
        failed += result["status"] == "failed"
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

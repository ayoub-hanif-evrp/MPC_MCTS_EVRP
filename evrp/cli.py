"""Stable command-line interface for the final-paper experiment track."""

import argparse
import json
import os

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

from . import studies
from .experiments import load_config, run_single
from .storage import ROOT, load_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "smoke", "run", "screening", "development", "final", "main", "ablations", "realtime"):
        item = sub.add_parser(command)
        item.add_argument("--config", default=str(ROOT / "configs" / f"{'debug' if command == 'run' else 'validation' if command == 'validate' else 'final' if command in {'development', 'final'} else command}.yaml"))
        item.add_argument("--output", default=f"results/{command}")
        if command == "run":
            item.add_argument("--instance", required=True)
            item.add_argument("--algorithm")
            item.add_argument("--dynamicity", type=float)
            item.add_argument("--scenario-seed", type=int)
            item.add_argument("--algorithm-seed", type=int)
            item.add_argument("--scenario")
        if command == "screening":
            item.add_argument("--stage", choices=("1", "2", "all"), default="all")
        if command == "final":
            item.add_argument("--execute", action="store_true")
            item.add_argument("--development", default="results/development")
        if command in studies.GATED_STUDIES:
            item.add_argument("--execute", action="store_true")
            item.add_argument("--screening", default="results/screening")
            item.add_argument("--screening-config", default=str(ROOT / "configs/screening.yaml"))
    for command in ("aggregate", "tables", "plot", "audit"):
        item = sub.add_parser(command)
        item.add_argument("--input", default="results/screening/stage2/runs" if command in {"aggregate", "audit"} else "results/summaries")
        item.add_argument("--output", default=f"results/{'summaries' if command == 'aggregate' else 'figures' if command == 'plot' else command}")
        item.add_argument("--study", default="screening_stage2")
    args = parser.parse_args(argv)
    try:
        output = studies.result_path(args.output)
        if args.command in {"aggregate", "tables", "plot", "audit"}:
            inputs = studies.result_path(args.input)
            if args.command == "aggregate":
                from .analysis import aggregate
                result = aggregate(inputs, output)
            elif args.command == "tables":
                from .analysis import export_tables
                result = {"table_pairs": len(export_tables(inputs, output))}
            elif args.command == "plot":
                from .plotting import make_figures
                result = {"figures": len(make_figures(inputs, output, args.study))}
            else:
                from .audit import audit_directory
                frame = audit_directory(inputs, output)
                print(frame.to_string(index=False))
                if frame.empty or not frame.structural_valid.all():
                    raise SystemExit(1)
                return
        else:
            config = load_config(args.config)
            if args.command == "validate":
                from .reference import ReferenceConfig
                from .validation import validate_references
                frame = validate_references(output, ReferenceConfig(
                    config.get("reference_solver_multistarts", 3),
                    config.get("reference_improvement_passes", 1),
                    config.get("reference_seed", 0), config.get("reference_label_limit", 24)))
                print(frame.to_string(index=False))
                if frame.empty or not frame.validation_status.eq("passed").all():
                    raise SystemExit(1)
                return
            if args.command == "run":
                for arg, key in (("algorithm", "algorithm"), ("dynamicity", "dynamicity"),
                                 ("scenario_seed", "scenario_seed"), ("algorithm_seed", "experiment_seed"),
                                 ("scenario", "scenario_path")):
                    if getattr(args, arg) is not None:
                        config[key] = getattr(args, arg)
                path = run_single(args.instance, studies.runtime_config(config), output)
                record = load_json(path)
                result = {"path": str(path), "status": record["status"],
                          "metrics": record["metrics"], "error": record.get("error")}
            elif args.command == "screening":
                result = studies.run_screening(config, output, stage=args.stage)
            elif args.command == "development":
                result = studies.run_final_development(config, output)
            elif args.command == "final":
                result = studies.run_final_holdout(config, output, execute=args.execute, development=args.development)
            else:
                result = studies.run_study(args.command, config, output,
                    execute=args.command == "smoke" or args.execute,
                    screening=getattr(args, "screening", "results/screening"),
                    screening_config=load_config(args.screening_config) if args.command in studies.GATED_STUDIES else None)
        print(json.dumps(result, indent=2), flush=True)
        if result.get("status") in {"FAIL", "failed"}:
            raise SystemExit(1)
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()

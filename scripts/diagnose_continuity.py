"""Bounded follow-up only, with a killable single-process timeout per case."""

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from pathlib import Path
import subprocess
import sys
from time import perf_counter

from evrp.audit import audit_record
from evrp.experiments import run_single, source_fingerprint
from evrp.storage import ROOT, load_json, save_json
from scripts.diagnose_v2 import BASE, INSTANCES, ALGORITHMS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stage", choices=("probe", "controls"), default="probe")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--case", choices=INSTANCES)
    parser.add_argument("--dod", type=float, choices=(0., .5))
    parser.add_argument("--algorithm", choices=ALGORITHMS, default="COORDINATED_MPC_MCTS")
    parser.add_argument("--source")
    parser.add_argument("--insertion", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        print("4 probes or 36 bounded controls only. Explicit --execute required; no paper campaign.")
        return
    if not 0 < args.timeout <= 300:
        parser.error("Timeout must be in (0, 300] seconds")
    code = source_fingerprint()
    root = ROOT / "results/development_route_continuity" / code[:12]
    if args.insertion:
        root = root / "insertion"
    if args.case:
        if code != args.source or args.dod is None:
            raise RuntimeError("Worker source/configuration mismatch")
        config = {**BASE, "study": "route_continuity_development", "route_continuity": True,
                  "route_insertion": args.insertion,
                  "mcts_iterations": 32, "dynamicity": args.dod, "algorithm": args.algorithm,
                  "execution_profile": "sequential_development"}
        path = run_single(args.case, config, root / "raw")
        errors = audit_record(load_json(path))
        if errors:
            raise RuntimeError(errors)
        print(path, flush=True)
        return
    cases = ([(name, dod, "COORDINATED_MPC_MCTS") for name, dod in
              (("c201_21", 0.), ("c201_21", .5), ("r101_21", 0.), ("rc101_21", 0.))]
             if args.stage == "probe" else
             [(name, dod, algorithm) for name in INSTANCES for dod in (0., .5) for algorithm in ALGORITHMS])
    manifest = dict(source_sha256=code, stage=args.stage, planned=len(cases), records=[],
                    status="running", timeout_seconds=args.timeout, full_campaign_started=False)
    for name, dod, algorithm in cases:
        if source_fingerprint() != code:
            raise RuntimeError("Source changed during diagnostic execution")
        save_json(root / f"{args.stage}_manifest.json", manifest)
        start = perf_counter()
        command = [sys.executable, "-m", "scripts.diagnose_continuity", "--execute", "--case", name,
                   "--dod", str(dod), "--algorithm", algorithm, "--source", code]
        if args.insertion:
            command.append("--insertion")
        try:
            completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                       timeout=args.timeout, check=True)
            path = Path(completed.stdout.strip().splitlines()[-1])
            record = load_json(path)
            errors = audit_record(record)
            if record["status"] != "completed" or errors:
                raise RuntimeError(f"Failed record: {path}: {errors}")
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, RuntimeError) as error:
            manifest.update(status="stopped", error=str(error), failed_case=[name, dod, algorithm])
            if isinstance(error, subprocess.CalledProcessError):
                manifest["worker_stderr"] = error.stderr
            save_json(root / f"{args.stage}_manifest.json", manifest)
            raise
        metrics = record["metrics"]
        row = dict(instance=name, DoD=dod, algorithm=algorithm, path=str(path.relative_to(ROOT)),
                   elapsed_seconds=perf_counter()-start, audit_errors=errors, metrics=metrics)
        manifest["records"].append(row)
        save_json(root / f"{args.stage}_manifest.json", manifest)
        print(f"{len(manifest['records'])}/{len(cases)} {name} DoD={dod} {algorithm} "
              f"served={metrics['customers_served']} EV={metrics['vehicles_activated']} "
              f"waits={metrics['wait_selected']} planning={metrics['total_planning_time']:.2f}s", flush=True)
    manifest["status"] = "completed"
    save_json(root / f"{args.stage}_manifest.json", manifest)


if __name__ == "__main__":
    main()

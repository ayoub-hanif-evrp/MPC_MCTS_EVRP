"""Explicitly bounded diagnostic campaign. Never invokes the paper executor."""

import os
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1"

import argparse
from pathlib import Path
from statistics import median
from time import perf_counter
from concurrent.futures import ProcessPoolExecutor

from evrp.audit import audit_record
from evrp.experiments import run_single, source_fingerprint
from evrp.storage import load_json, save_json, identifier

INSTANCES = ("c101_21", "c201_21", "r101_21", "r201_21", "rc101_21", "rc201_21")
ALGORITHMS = ("GREEDY", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS")
BASE = dict(study="v2_diagnostic", algorithm="COORDINATED_MPC_MCTS", dynamicity=.5,
            scenario_seed=0, experiment_seed=0, fleet_mode="lazy_reserve",
            require_root_coverage=True, max_idle_wait=10, mcts_iterations=64,
            prediction_horizon=5, top_L=3, candidate_limit=12,
            station_candidate_limit=4, charge_target_limit=5, charging_mode="partial",
            trace_level="summary", diagnostics=True, parallel_agents=False,
            execution_profile="concurrent_diagnostic", result_compression="gzip")


def worker(name, config, directory, code):
    if source_fingerprint() != code:
        raise RuntimeError("Scientific source changed during diagnostics")
    start = perf_counter()
    path = run_single(name, config, directory)
    return str(path), perf_counter()-start


def choose_budget(records):
    budgets = (32, 64, 96)
    lookup = {(r["metadata"]["instance"], r["requested_config"]["mcts_iterations"]): r["metrics"] for r in records}
    medians = {b: median(lookup[i, b]["customers_served"] for i in INSTANCES) for b in budgets}
    reference = max(budgets, key=lambda b: (medians[b], b))
    comparisons = []
    for b in budgets:
        ratios = []
        for i in INSTANCES:
            a, ref = lookup[i, b], lookup[i, reference]
            if (a["customers_served"], a["vehicles_activated"]) == (ref["customers_served"], ref["vehicles_activated"]):
                ratios.append(a["total_distance"] / ref["total_distance"])
        eligible = medians[b] >= medians[reference]-1 and bool(ratios) and max(ratios) <= 1.05
        comparisons.append(dict(budget=b, median_service=medians[b], equal_outcome_pairs=len(ratios),
                                worst_distance_ratio=max(ratios) if ratios else None, eligible=eligible))
    selected = next((r["budget"] for r in comparisons if r["eligible"]), 64)
    return dict(budget=selected, reference=reference, comparisons=comparisons,
                rule="Smallest budget within one customer of best median service, with at least one equal-service/equal-EV pair and all paired distances within 5%; largest-budget median tie break; ambiguous fallback 64. Development calibration only.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--stage", choices=("calibration", "all"), default="all")
    parser.add_argument("--output", type=Path, default=Path(os.environ["LOCALAPPDATA"])/"EVRP/diagnostic_v2")
    args = parser.parse_args()
    if not args.execute:
        print("Only six specified instances, seeds 0: 12 oracle + 66 unique online conditions. No full paper campaign. Add --execute.")
        return
    code = source_fingerprint()
    archive = args.output / code[:12]
    completed, memberships, records, futures = {}, [], [], {}
    pool = None

    def enqueue(cases):
        for name, changes, phase in cases:
            config = {**BASE, **changes}
            key = identifier((name, config))
            if key not in completed and key not in futures:
                futures[key] = pool.submit(worker, name, config, archive/"raw", code)

    def execute(name, changes, phase):
        if source_fingerprint() != code:
            raise RuntimeError("Scientific source changed during diagnostics; stopping")
        config = {**BASE, **changes}
        key = identifier((name, config))
        memberships.append(dict(key=key, phase=phase, instance=name))
        if key in completed:
            return completed[key]
        started = perf_counter()
        if key in futures:
            path, seconds = futures.pop(key).result()
        else:
            path = run_single(name, config, archive / ("oracle" if phase == "oracle" else "raw"))
            seconds = perf_counter()-started
        record = load_json(path)
        errors = audit_record(record)
        if record["status"] != "completed" or errors:
            raise RuntimeError(f"Diagnostic stopped: {name}: {record.get('error')}; {errors}")
        if phase == "oracle" and record["metrics"]["customers_unserved"]:
            raise RuntimeError("Oracle failed; online diagnostics forbidden")
        completed[key] = record
        records.append(dict(key=key, path=str(path), instance=name, seconds=seconds,
                            algorithm=config["algorithm"], DoD=config["dynamicity"], budget=config["mcts_iterations"],
                            fleet=config["fleet_mode"], horizon=config["prediction_horizon"], audit_errors=errors))
        save_json(archive / "progress.json", dict(source_sha256=code, completed=len(records), records=records,
                                                  memberships=memberships, status="running"))
        m = record["metrics"]
        print(f"{len(records):02d} {phase} {name} DoD={config['dynamicity']} {config['algorithm']} b={config['mcts_iterations']} served={m['customers_served']} EV={m['vehicles_activated']} planning={m['total_planning_time']:.2f}s", flush=True)
        return record

    for name in INSTANCES:
        for dod in (0., .5):
            execute(name, dict(algorithm="ORACLE_REFERENCE", dynamicity=dod), "oracle")
    from evrp.runtime import worker_capacity
    # Separate independent jobs only; no inner agent pools. Four bounded workers.
    capacity = worker_capacity(measured_peak_mib=512, requested=4)
    if capacity["workers"] < 1:
        raise RuntimeError("Insufficient memory for diagnostic workers")
    print("Diagnostic resources:", capacity, flush=True)
    pool = ProcessPoolExecutor(max_workers=capacity["workers"])
    cases = [(name, dict(mcts_iterations=b), "calibration") for name in INSTANCES for b in (32, 64, 96)]
    enqueue(cases)
    try:
        calibration = [execute(*case) for case in cases]
    except BaseException:
        pool.shutdown(wait=True, cancel_futures=True)
        raise
    selection = choose_budget(calibration)
    save_json(archive / "selection.json", selection)
    print("Budget selection:", selection, flush=True)
    budget = selection["budget"]
    if args.stage == "all":
        cases = []
        for name in INSTANCES:
            for dod in (0., .5):
                for algorithm in ALGORITHMS:
                    cases.append((name, dict(algorithm=algorithm, dynamicity=dod, mcts_iterations=budget), "main"))
            cases.append((name, dict(fleet_mode="fixed_reference", mcts_iterations=budget), "fleet_control"))
            for horizon in (1, 3):
                cases.append((name, dict(prediction_horizon=horizon, mcts_iterations=budget), "horizon"))
        enqueue(cases)
        try:
            for case in cases:
                execute(*case)
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
    else:
        pool.shutdown(wait=True)
    payload = dict(source_sha256=code, completed=len(records), records=records, memberships=memberships,
                   selection=selection, resource=capacity, status="completed", paper_campaign_authorized=False)
    save_json(archive / "progress.json", payload)
    save_json("results/paper_v2/diagnostic_manifest.json", payload)
    print("Diagnostic campaign complete. Full paper campaign remains unauthorized.", flush=True)


if __name__ == "__main__":
    main()

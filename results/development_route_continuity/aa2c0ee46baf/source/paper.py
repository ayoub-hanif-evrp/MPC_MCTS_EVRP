"""Compact study membership, audited reuse, calibration and guarded execution."""

from dataclasses import asdict
from itertools import product
from pathlib import Path
from statistics import median
from time import perf_counter
import math
import os
import shutil

from .experiments import grid_cases, run_single, simulation_config, source_fingerprint
from .storage import BENCHMARK, ROOT, identifier, load_json, save_json

CALIBRATION = ("c101_21", "c201_21", "r101_21", "r201_21", "rc101_21", "rc201_21")
BALANCED = ("c101_21", "c109_21", "c201_21", "c208_21", "r101_21", "r112_21",
            "r201_21", "r211_21", "rc101_21", "rc108_21", "rc201_21", "rc208_21")
ALGORITHMS = ("GREEDY", "MPC_MCTS_H1", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS")


def canonical_config(changes=None):
    # Study membership and runtime location are not scientific run identity.
    base = dict(study="paper", algorithm="COORDINATED_MPC_MCTS", dynamicity=.5,
                scenario_seed=0, experiment_seed=0, prediction_horizon=5, control_horizon=1,
                candidate_limit=12, top_L=3, mcts_iterations=32, uct_c=1.4,
                budget_mode="iterations", mcts_time_limit=.5, charging_mode="partial",
                charge_fractions=[.5, .75, 1.0], station_candidate_limit=4, charge_target_limit=5,
                action_space_reduction=True, cache_transitions=True, trace_level="summary",
                symmetry_reuse=False, parallel_agents=False, workers=2,
                dynamic_selection_mode="exact_count", reference_solver_multistarts=3,
                reference_improvement_passes=1, reference_seed=0, result_compression="gzip")
    for key, value in (changes or {}).items():
        if key in base and key not in {"study"}:
            base[key] = value
    return base


def experiment_key(instance, config):
    return identifier(dict(instance=instance, config=canonical_config(config)))


def paper_plan(config):
    base = canonical_config({k: v for k, v in config.items() if k != "workers"})
    memberships, jobs = [], {}

    def add(study, instance, changes=None, factor="baseline"):
        effective = canonical_config({**base, **(changes or {})})
        key = experiment_key(instance, effective)
        jobs.setdefault(key, dict(key=key, instance=instance, config=effective,
                                  isolated=effective["budget_mode"] == "wall_clock" or effective["parallel_agents"]))
        memberships.append(dict(study=study, factor=factor, key=key, instance=instance))

    for instance, algorithm in product(sorted(p.stem for p in BENCHMARK.glob("*_21.txt")), ALGORITHMS):
        add("A", instance, dict(algorithm=algorithm))
    for instance, dod, seed, algorithm in product(BALANCED, (0, .25, .5, .75), (0, 1), ALGORITHMS):
        add("B", instance, dict(dynamicity=dod, scenario_seed=seed, algorithm=algorithm))
    for instance, seed, algorithm in product(CALIBRATION, range(5), ALGORITHMS[1:]):
        add("C", instance, dict(experiment_seed=seed, algorithm=algorithm))
    factors = dict(prediction_horizon=(1, 3, 5), top_L=(1, 3, 5), mcts_iterations=(8, 16, 32, 64),
                   charging_mode=("full", "partial"), algorithm=("INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS"))
    for instance in CALIBRATION:
        for factor, values in factors.items():
            for value in values:
                add("D", instance, {factor: value}, factor)
    for instance, seconds, seed in product(("c103C15", "c101_21", "r101_21"), (.05, .1, .25, .5), (0, 1)):
        add("E", instance, dict(budget_mode="wall_clock", mcts_time_limit=seconds, experiment_seed=seed))
    return list(jobs.values()), memberships


def select_budget(rows):
    valid = [r for r in rows if r.get("status") == "completed" and not r.get("audit_errors")]
    by = {(r["instance"], r["iterations"]): r for r in valid}
    budgets = (8, 16, 32, 64)
    if any((i, b) not in by for i, b in product(CALIBRATION, budgets)) or len(by) != 24:
        return dict(budget=32, reason="Incomplete or failed calibration; fallback only, gate remains closed", clear=False)
    medians = {b: median(by[i, b]["customers_served"] for i in CALIBRATION) for b in budgets}
    reference = max(budgets, key=lambda b: (medians[b], b))
    comparisons = []
    for budget in budgets:
        ratios = []
        for instance in CALIBRATION:
            a, b = by[instance, budget], by[instance, reference]
            if (a["customers_served"], a["vehicles_activated"]) == (b["customers_served"], b["vehicles_activated"]):
                ratios.append(a["total_distance"] / b["total_distance"] if b["total_distance"] else
                              1.0 if not a["total_distance"] else float("inf"))
        eligible = bool(ratios) and all(math.isfinite(r) and r <= 1.05 for r in ratios)
        comparisons.append(dict(budget=budget, median_service=medians[budget], equal_outcome_pairs=len(ratios),
                                worst_distance_ratio=max(ratios) if ratios and all(math.isfinite(r) for r in ratios) else None,
                                eligible=medians[budget] >= medians[reference]-1 and eligible))
    chosen = next((r["budget"] for r in comparisons if r["eligible"]), 32)
    return dict(budget=chosen, reference_budget=reference, comparisons=comparisons, clear=True,
                reason="Smallest budget within one median service and 5% distance on every equal-service/equal-fleet pair")


def reusable_records(paths, source=None):
    from .audit import audit_record
    reusable = {}
    source = source or source_fingerprint()
    for root in paths:
        if not Path(root).exists():
            continue
        for path in sorted(Path(root).rglob("*.json.gz")):
            if any(p.startswith("archive") for p in path.parts):
                continue
            record = load_json(path)
            if record.get("status") != "completed" or record.get("provenance", {}).get("source_sha256") != source:
                continue
            if audit_record(record):
                continue
            key = experiment_key(record["identity"]["instance"], record["requested_config"])
            reusable.setdefault(key, str(path.resolve()))
    return reusable


def reference_cached(instance, config):
    from hashlib import sha256
    from .reference import ReferenceConfig
    from .versions import REFERENCE_SOLVER_VERSION
    reference = ReferenceConfig(config.get("reference_solver_multistarts", 3),
                                config.get("reference_improvement_passes", 1), config.get("reference_seed", 0),
                                config.get("reference_label_limit", 24))
    key = identifier(dict(instance=sha256((BENCHMARK / (instance + ".txt")).read_bytes()).hexdigest(),
                          config=asdict(reference), reference_solver_version=REFERENCE_SOLVER_VERSION))[:16]
    return (ROOT / "data/reference_schedules" / f"{instance}_{key}.json").exists()


def estimate(config, output=None, workers=4, calibration=None):
    from .runtime import worker_capacity
    jobs, memberships = paper_plan(config) if config.get("study") == "paper" else (
        [dict(key=experiment_key(i, c), instance=i, config=c,
              isolated=c.get("budget_mode") == "wall_clock" or c.get("parallel_agents", False))
         for i, c in grid_cases(config, config.get("study") == "ablations")], [])
    report_path = Path(config.get("calibration_report", "results/performance/calibration.json"))
    report = calibration if calibration is not None else load_json(report_path) if report_path.exists() else {}
    current = source_fingerprint()
    calibrated = report.get("source_sha256") == current
    rows = report.get("rows", []) if calibrated else []
    roots = [Path(output or "results/paper") / "raw"]
    roots.extend({str(Path(r["path"]).parent) for r in rows if "path" in r})
    reusable = reusable_records(roots, current)
    cold_path = ROOT / "results/performance/reference_cold.json"
    cold = load_json(cold_path) if cold_path.exists() else []
    cold = [r for r in cold if r.get("identical_reference") and r.get("source_sha256") == current]
    resource = worker_capacity(max([r.get("peak_memory_mib", 256) for r in rows + cold] or [256]), workers)
    count = resource["workers"]
    measurements = [r for r in rows if r.get("status") == "completed" and not r.get("audit_errors")]
    measured_budget = report.get("selection", {}).get("budget", config.get("mcts_iterations", 32))
    samples = [r for r in measurements if r["iterations"] == measured_budget]
    fallback = max((r["wall_seconds"] for r in samples), default=None)
    by = {(r["instance"], r["iterations"]): r["wall_seconds"] for r in measurements}
    throughput = isolated = 0.0
    remaining = [j for j in jobs if j["key"] not in reusable]
    max_replans = max((r["agent_replans"] for r in samples), default=0)
    for job in remaining:
        cfg = job["config"]
        if fallback is None:
            continue
        budget = cfg.get("mcts_iterations", 32)
        seconds = by.get((job["instance"], budget), fallback * budget / measured_budget)
        # Conservative proxy for algorithms not yet timed. No invented speedup.
        if cfg.get("charging_mode") == "full":
            seconds *= 2
        if cfg.get("budget_mode") == "wall_clock":
            # Budgets stop between simulations; allow one simulation overshoot per call.
            seconds = max_replans * (cfg.get("mcts_time_limit", .5) + fallback / max(1, max_replans)) + 2
        if job["isolated"]:
            isolated += seconds
        else:
            throughput += seconds
    missing_instances = {j["instance"] for j in remaining if not reference_cached(j["instance"], j["config"])}
    import re
    family = lambda name: re.match(r"[a-z]+[12]", name).group(0)
    preparation_samples = list(report.get("preparations", []))
    preparation_samples = [r for r in preparation_samples if r["seconds"] > 1]
    cold_families = {family(r["instance"]) for r in cold}
    preparation_samples = [r for r in preparation_samples if family(r["instance"]) not in cold_families] + cold
    worst_preparation = max((p["seconds"] for p in preparation_samples), default=None)
    dependency_seconds = sum(max((p["seconds"] for p in preparation_samples if family(p["instance"]) == family(i)),
                                 default=worst_preparation or 0) for i in missing_instances)
    if missing_instances and worst_preparation is None:
        fallback = None
    sequential = throughput + isolated + dependency_seconds if fallback is not None else None
    parallel = ((throughput + dependency_seconds) / max(1, count) / .7 + isolated) if sequential is not None and count else None
    studies = {}
    seen = set()
    for study in ("A", "B", "C", "D", "E"):
        members = [m for m in memberships if m["study"] == study]
        keys = {m["key"] for m in members}
        if members:
            studies[study] = dict(table_rows=len(members), unique_conditions=len(keys),
                                  additional_runs=len(keys-seen), reusable=len(keys & reusable.keys()))
        seen.update(keys)
    return dict(planned=len(jobs), reusable=len(jobs)-len(remaining), remaining=len(remaining),
                estimated_sequential_seconds=sequential, estimated_parallel_seconds=parallel,
                dependency_seconds=dependency_seconds, cold_reference_instances=len(missing_instances),
                resource=resource, studies=studies,
                calibration_current=calibrated, selected_budget=measured_budget,
                assumption="Worst measured coordinated time for untimed algorithms/instances; 70% outer efficiency; realtime isolated; cold preparation by family (worst observed fallback), independent instances prepared in parallel",
                uncertainty="Extrapolation, not a guarantee. Untested dynamicity, full charging and instance geometry can change runtime.")


def validate_launch(config, report, estimate_result, execute=False):
    if not execute:
        raise RuntimeError("Planning only. Review estimate and pass --execute explicitly to launch")
    if report.get("source_sha256") != source_fingerprint():
        raise RuntimeError("Missing or stale calibration; remeasure current source before launching")
    rows = report.get("rows", [])
    if len(rows) != 24 or any(r.get("status") != "completed" or r.get("audit_errors") for r in rows):
        raise RuntimeError("All 24 calibration records must pass integrity checks")
    selected = report["selection"]["budget"]
    if select_budget(rows)["budget"] != selected:
        raise RuntimeError("Calibration selection differs from the predefined rule")
    if config.get("mcts_iterations", 32) != selected:
        raise RuntimeError("Paper budget must equal the predefined calibration selection")
    sample = next(r for r in rows if r["instance"] == "c101_21" and r["iterations"] == selected)
    from .audit import audit_record
    expected = canonical_config({k: v for k, v in config.items() if k != "workers"})
    for row in rows:
        raw = load_json(row["path"])
        if audit_record(raw) or raw["provenance"]["source_sha256"] != report["source_sha256"]:
            raise RuntimeError("Calibration raw record failed source/integrity validation")
        measured = canonical_config({**raw["requested_config"], "mcts_iterations": selected})
        if measured != expected:
            raise RuntimeError("Paper method differs from the calibrated configuration")
    if sample["wall_seconds"] > config.get("performance_gate_seconds", 60):
        raise RuntimeError("c101_21 performance gate failed; no paper campaign launched")
    hours = estimate_result["estimated_parallel_seconds"]
    if hours is None or hours > config.get("maximum_paper_hours", 6)*3600:
        raise RuntimeError("Paper runtime is unknown or exceeds the few-hour gate; no campaign launched")
    if estimate_result["resource"]["workers"] < 1:
        raise RuntimeError("Insufficient free memory to launch a worker")


def _worker(job, output):
    start = perf_counter()
    config = {**job["config"], "execution_profile": "isolated" if job["isolated"] else "concurrent"}
    path = run_single(job["instance"], config, Path(output) / "raw")
    record = load_json(path)
    from .audit import audit_record
    errors = audit_record(record)
    if errors or record["status"] != "completed":
        raise RuntimeError(f"Failed run {path}: {errors or record.get('error')}")
    return dict(key=job["key"], path=str(path.resolve()), seconds=perf_counter()-start,
                timing_context="isolated" if job["isolated"] else "concurrent", status="completed")


def _prepare_group(group):
    from .experiments import prepare
    instance, configs = group
    start = perf_counter()
    for config in configs:
        prepare(instance, config)
    return dict(instance=instance, seconds=perf_counter()-start, scenarios=len(configs))


def execute_paper(config, output, workers=4, execute=False):
    if execute:
        raise RuntimeError("V2 scientific review required. The 704-condition campaign is disabled; run only scripts.diagnose_v2 until the diagnostic report is reviewed.")
    from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
    from .campaign import exclusive_runner
    from .experiments import prepare
    from .runtime import available_memory_mib
    report = load_json(config.get("calibration_report", "results/performance/calibration.json"))
    estimation = estimate(config, output, workers, report)
    validate_launch(config, report, estimation, execute)
    jobs, memberships = paper_plan(config)
    directory = Path(output).resolve()
    if directory.is_relative_to((ROOT / "results/campaigns/final").resolve()):
        raise ValueError("Cancelled campaign outputs must not be overwritten")
    source = source_fingerprint()
    signature = identifier(dict(source=source, jobs=jobs))
    manifest_path = directory / "manifest.json"
    if manifest_path.exists() and load_json(manifest_path)["signature"] != signature:
        raise RuntimeError("Changed method/configuration; choose a new output directory")
    with exclusive_runner(directory / "runner.lock"):
        save_json(manifest_path, dict(signature=signature, source_sha256=source, jobs=jobs,
                                     memberships=memberships, estimate=estimation))
        roots = [directory / "raw"] + list({str(Path(r["path"]).parent) for r in report["rows"]})
        paths = reusable_records(roots, source)
        events = []
        ledger = directory / "execution.json"
        if ledger.exists():
            events = load_json(ledger)
        todo = [j for j in jobs if j["key"] not in paths]
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[name] = "1"
        resource = estimation["resource"]
        # One worker owns every scenario for its instance, avoiding cache-write races.
        groups = {}
        for job in todo:
            groups.setdefault(job["instance"], {})[(job["config"]["dynamicity"], job["config"]["scenario_seed"])] = job["config"]
        with ProcessPoolExecutor(max_workers=resource["workers"]) as preparers:
            setup = list(preparers.map(_prepare_group, [(i, list(c.values())) for i, c in sorted(groups.items())]))
        save_json(directory / "preparation_timings.json", setup)
        def record(event):
            paths[event["key"]] = event["path"]
            events.append(event)
            save_json(ledger, events)
            save_json(directory / "status.json", dict(status="running", completed=sum(j["key"] in paths for j in jobs), total=len(jobs)))
            print(event, flush=True)
        def revision_guard():
            if source_fingerprint() != source:
                raise RuntimeError("Source changed during campaign")
        throughput = [j for j in todo if not j["isolated"]]
        with ProcessPoolExecutor(max_workers=resource["workers"]) as pool:
            pending, active = iter(throughput), {}
            exhausted = False
            while not exhausted or active:
                revision_guard()
                while len(active) < resource["workers"] and not exhausted:
                    if available_memory_mib() < 512 + resource["per_worker_mib"] and active:
                        break
                    job = next(pending, None)
                    if job is None:
                        exhausted = True
                        break
                    active[pool.submit(_worker, job, str(directory))] = job
                done, _ = wait(active, timeout=5, return_when=FIRST_COMPLETED)
                for future in done:
                    record(future.result())
                    del active[future]
        # All outer processes have exited before realtime measurement starts.
        for job in todo:
            if job["isolated"]:
                revision_guard()
                record(_worker(job, directory))
        render_studies(directory, memberships, paths)
        save_json(directory / "status.json", dict(status="completed", completed=len(jobs), total=len(jobs)))


def render_studies(directory, memberships, paths):
    """Materialize study views from shared raw records without rerunning a condition."""
    import pandas as pd
    from .analysis import aggregate, export_tables
    from .plotting import make_figures, make_realtime_figures
    destination = ROOT / "results/paper"
    raw_context = [dict(key=key, path=path, execution_profile=load_json(path)["requested_config"].get("execution_profile", "unspecified"))
                   for key, path in paths.items()]
    destination.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(raw_context).to_csv(destination / "timing_context.csv", index=False)
    for study in ("A", "B", "C", "D", "E"):
        selected = [m for m in memberships if m["study"] == study]
        view = Path(directory) / "study_views" / study
        for member in selected:
            record = load_json(paths[member["key"]])
            # Derived records retain physical/scenario data but have study-specific
            # provenance-bound IDs so repeated baseline cells cannot inflate groups.
            from .experiments import run_identity, result_sections
            cfg = {**record["requested_config"], "study": "ablations" if study == "D" else "realtime" if study == "E" else study,
                   "ablation_factor": member["factor"]}
            record["requested_config"] = cfg
            ident = record["identity"]
            identity = run_identity(ident["instance"], ident["instance_sha256"], ident["scenario_hash"],
                                    cfg, record["provenance"]["source_sha256"], record["provenance"]["git_commit"])
            from .scenario import DynamicScenario
            from .instance import load_instance
            instance = load_instance(BENCHMARK / (ident["instance"] + ".txt"))
            scenario = DynamicScenario.load(record["scenario_path"], instance)
            record["provenance"]["derived_from_run_id"] = ident["run_id"]
            result_sections(record, identity, scenario, instance)
            save_json(view / "raw" / (identity["run_id"] + ".json.gz"), record)
        summaries = view / "summaries"
        aggregate(view / "raw", summaries)
        export_tables(summaries, view / "tables")
        if study == "E":
            make_realtime_figures(summaries, view / "figures")
        else:
            make_figures(summaries, view / "figures", "ablations" if study == "D" else study)
        for folder in ("summaries", "tables", "figures"):
            shutil.copytree(view / folder, destination / study / folder, dirs_exist_ok=True)
    save_json(destination / "memberships.json", memberships)

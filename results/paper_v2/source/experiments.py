"""Resumable, provenance-bound research runs and YAML configuration loading."""

from dataclasses import asdict, replace
from importlib.metadata import version
from itertools import product
from pathlib import Path
import json
import platform
import traceback
import subprocess
from datetime import datetime, timezone

import yaml

from .instance import load_instance
from .mpc import MPCConfig
from .reference import ReferenceConfig, ReferenceSchedule, solve_reference
from .scenario import DynamicScenario, generate
from .simulator import EventDrivenSimulator, ExperimentResult, SimulationConfig, SimulationEvent
from .storage import BENCHMARK, ROOT, benchmark_hashes, identifier, save_json, load_json
from .versions import OBJECTIVE_VERSION, REFERENCE_SOLVER_VERSION, RESULT_SCHEMA_VERSION, SCENARIO_GENERATOR_VERSION


def load_config(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML mapping")
    return data


def simulation_config(config: dict) -> SimulationConfig:
    mapping = {"prediction_horizon": "prediction_horizon", "control_horizon": "control_horizon",
               "top_L": "top_l", "candidate_limit": "candidate_limit", "mcts_iterations": "iterations",
               "uct_c": "uct_c", "budget_mode": "budget_mode", "mcts_time_limit": "time_limit",
               "charging_mode": "charging_mode", "charge_fractions": "charge_fractions",
               "station_candidate_limit": "station_candidate_limit", "charge_target_limit": "charge_target_limit",
               "action_space_reduction": "action_space_reduction", "cache_transitions": "cache_transitions",
               "require_root_coverage": "require_root_coverage", "max_idle_wait": "max_idle_wait"}
    kwargs = {target: config[source] for source, target in mapping.items() if source in config}
    if "charge_fractions" in kwargs:
        kwargs["charge_fractions"] = tuple(kwargs["charge_fractions"])
    return SimulationConfig(algorithm=config.get("algorithm", "COORDINATED_MPC_MCTS"),
                            experiment_seed=config.get("experiment_seed", 0),
                            parallel_agents=config.get("parallel_agents", False),
                            workers=config.get("workers", 2), mpc=MPCConfig(**kwargs),
                            trace_level=config.get("trace_level", "full"),
                            symmetry_reuse=config.get("symmetry_reuse", False),
                            fleet_mode=config.get("fleet_mode", "fixed_reference"),
                            diagnostics=config.get("diagnostics", False))


def source_fingerprint() -> str:
    return identifier({p.name: p.read_text(encoding="utf-8") for p in sorted((ROOT / "evrp").glob("*.py"))})


def prepare(instance_name: str, config: dict):
    path = BENCHMARK / (instance_name if instance_name.endswith(".txt") else instance_name + ".txt")
    if path.resolve().parent != BENCHMARK.resolve():
        raise ValueError("Only the repository Schneider benchmark is supported")
    instance = load_instance(path)
    ref_config = ReferenceConfig(config.get("reference_solver_multistarts", 3),
                                 config.get("reference_improvement_passes", 1),
                                 config.get("reference_seed", 0), config.get("reference_label_limit", 24))
    key = identifier({"instance": instance.sha256, "config": asdict(ref_config),
                      "reference_solver_version": REFERENCE_SOLVER_VERSION})[:16]
    ref_path = ROOT / "data" / "reference_schedules" / f"{instance.name}_{key}.json"
    if ref_path.exists():
        reference = ReferenceSchedule.load(ref_path, instance)
    else:
        reference = solve_reference(instance, ref_config)
        reference.save(ref_path)
    scenario_key = identifier(dict(instance=instance.sha256, reference=reference.identifier,
                                  seed=config.get("scenario_seed", 0), dynamicity=config.get("dynamicity", 0.5),
                                  selection=config.get("dynamic_selection_mode", "exact_count"),
                                  generator=SCENARIO_GENERATOR_VERSION, objective=OBJECTIVE_VERSION))[:20]
    scenario_path = ROOT / "data" / "generated_scenarios" / f"{instance.name}_{scenario_key}.json"
    if config.get("scenario_path"):
        scenario = DynamicScenario.load(config["scenario_path"], instance)
        if scenario.reference_schedule_identifier != reference.identifier or scenario.fleet_size != reference.fleet_size:
            raise ValueError("Scenario must use the selected reference schedule and its fleet size")
        if scenario.scenario_seed != config.get("scenario_seed", 0) or scenario.target_DoD != config.get("dynamicity", 0.5):
            raise ValueError("Explicit scenario seed/DoD differs from requested configuration")
        scenario_path = Path(config["scenario_path"])
    elif scenario_path.exists():
        scenario = DynamicScenario.load(scenario_path, instance)
        if (scenario.reference_schedule_hash != reference.identifier or scenario.scenario_seed != config.get("scenario_seed", 0)
                or scenario.target_DoD != config.get("dynamicity", 0.5)
                or scenario.selection_mode != config.get("dynamic_selection_mode", "exact_count")):
            raise ValueError("Stale or mismatched cached scenario")
    else:
        scenario = generate(instance, reference, config.get("scenario_seed", 0), config.get("dynamicity", 0.5),
                            config.get("dynamic_selection_mode", "exact_count"))
        scenario.save(scenario_path)
    return instance, reference, scenario, scenario_path


def static_reference_result(instance, reference, scenario, config) -> ExperimentResult:
    steps = [s for r in reference.routes for s in r.steps]
    n = len(instance.customers)
    metrics = {"feasible": True, "customers_served": n, "customers_unserved": 0, "service_ratio": 1.0,
               "total_distance": reference.total_distance,
               "distance_per_served_customer": reference.total_distance / n if n else None,
               "vehicles_activated": reference.fleet_size, "total_charging_visits": sum(s.action.kind == "charge" for s in steps),
               "total_energy_charged": sum(s.energy_charged for s in steps),
               "total_charging_time": sum(s.charging_time for s in steps),
               "total_waiting_time": sum(s.waiting_time for s in steps), "final_return_feasibility": True,
               "time_window_violations": 0, "battery_violations": 0, "capacity_violations": 0,
               "decision_epochs": 0, "duplicate_customer_proposal_conflicts": 0, "conflicts_resolved": 0,
               "wait_selected": 0, "agent_replans": 0, "mcts_iterations": 0, "nodes_expanded": 0,
               "complete_service": True, "mean_unique_intention_coverage": 0,
               "vehicle_activations_caused_by_coordinator": 0,
               "duplicate_service_violations": 0, "hidden_information_violations": 0,
               **{name + "_planning_time": 0.0 for name in ("mean", "median", "p95", "maximum", "total")}}
    import re
    metadata = {"instance": instance.name, "instance_sha256": instance.sha256,
                "instance_family": re.match(r"([a-z]+[12])", instance.name).group(1).upper(),
                "number_of_customers": n, "number_of_stations": len(instance.infrastructure.stations),
                "K": reference.fleet_size, "DoD_target": scenario.target_DoD, "DoD_realized": scenario.realized_DoD,
                "scenario_seed": scenario.scenario_seed, "scenario_identifier": scenario.identifier,
                "algorithm_seed": config.get("experiment_seed", 0), "algorithm": "STATIC_REFERENCE",
                "reference_schedule_identifier": reference.identifier, "offline_reference_not_online_baseline": True}
    effective = asdict(simulation_config({**config, "algorithm": "GREEDY"}))
    effective["algorithm"] = "STATIC_REFERENCE"
    events = [SimulationEvent(t, "release", customer_id=c) for c, t in scenario.customer_release_times]
    for s in steps:
        events.extend((SimulationEvent(s.before.time, "dispatch", s.before.id, s.served, s.action),
                       SimulationEvent(s.after.time, "complete", s.before.id, s.served, s.action)))
    events.sort(key=lambda e: (e.time, {"release": 0, "complete": 1, "dispatch": 2}[e.kind]))
    return ExperimentResult(metadata, effective, metrics, events, steps, [], [], [])


def audit_result(result: ExperimentResult, instance, scenario) -> dict:
    """Independent trace checks; failed service remains a reported infeasible run."""
    from .model import EPS, Observation, transition
    from .reference import initial_vehicle

    releases = dict(scenario.customer_release_times)
    lazy = result.effective_config.get("fleet_mode") == "lazy_reserve"
    states = {} if lazy else {k: initial_vehicle(instance, k) for k in range(scenario.fleet_size)}
    seen = set()
    for step in sorted(result.steps, key=lambda s: (s.before.time, s.before.id)):
        if lazy and step.before.id not in states:
            assert 0 <= step.before.id < len(instance.customers), "Reserve fleet bound exceeded"
            states[step.before.id] = initial_vehicle(instance, step.before.id)
        assert step.before == states[step.before.id], "Discontinuous vehicle trace"
        legal = tuple(c for c in instance.customers if releases[c.id] <= step.before.time and c.id not in seen)
        actual = transition(step.before, step.action, Observation(step.before.time, instance.infrastructure, legal))
        assert actual == step, "Transition replay mismatch"
        states[step.before.id] = step.after
        if step.served:
            assert step.served not in seen, "Duplicate service"
            assert releases[step.served] <= step.before.time, "Action committed before release"
            seen.add(step.served)
    active, moving = {}, {}
    for event in result.events:
        if event.kind == "dispatch" and event.action.kind != "wait":
            assert event.vehicle_id not in moving, "Busy vehicle interrupted"
            moving[event.vehicle_id] = event.action
        elif event.kind == "complete":
            assert moving.pop(event.vehicle_id) == event.action, "Completion differs from commitment"
        if event.kind == "dispatch" and event.customer_id:
            assert event.customer_id not in active, "Duplicate customer commitment"
            active[event.customer_id] = event.vehicle_id
        elif event.kind == "complete" and event.customer_id:
            assert active.pop(event.customer_id) == event.vehicle_id
    assert not active and not moving, "Unfinished commitments"
    if result.metadata["algorithm"] not in {"STATIC_REFERENCE", "ORACLE_REFERENCE"}:
        assert len(result.decisions) == result.metrics["decision_epochs"], "Missing decision integrity evidence"
    for decision in result.decisions:
        assert all(releases[key] <= decision["time"] for key in decision["available"])
        assert not set(decision["available"]) & set(decision.get("committed_before", {}))
        assert set(decision.get("candidate_intents", ())) <= set(decision["available"]), "Hidden candidate intent"
        assert set(decision.get("background_intents", ())) <= set(decision["available"]), "Hidden background intent"
        selected_firsts = decision.get("selected_firsts", ())
        assert len(selected_firsts) == len(set(selected_firsts)), "Duplicate selected first action"
        if result.effective_config.get("trace_level") in {"summary", "none"}:
            assert "candidate_intents" in decision and "selected_firsts" in decision, "Missing compact integrity evidence"
        plans = list(decision["plans"].values())
        plans.extend(p for choices in decision.get("candidates", {}).values() for p in choices)
        for plan in plans:
            for action in plan["actions"]:
                if action["kind"] == "serve":
                    assert action["destination"] in decision["available"], "Hidden or committed customer in predicted tail"
        firsts = [p["actions"][0]["destination"] for p in decision["plans"].values()
                  if p["actions"][0]["kind"] == "serve"]
        assert len(firsts) == len(set(firsts)), "Duplicate selected first action"
    assert all(s.location == instance.infrastructure.depot and s.finished and s.time <= instance.infrastructure.depot.due + EPS
               for s in states.values()), "Vehicle did not return safely"
    assert len(seen) == result.metrics["customers_served"]
    import math
    metrics = result.metrics
    assert metrics["customers_unserved"] == len(instance.customers) - len(seen)
    assert math.isclose(metrics["total_distance"], sum(s.distance for s in result.steps), abs_tol=1e-6)
    assert metrics["vehicles_activated"] == sum(s.departed for s in states.values())
    if lazy:
        assert all(s.departed for s in states.values()), "Unused reserve instantiated as physical EV"
    assert math.isclose(metrics["service_ratio"], len(seen) / len(instance.customers), abs_tol=1e-9)
    assert sorted(result.unserved_customers) == sorted(c.id for c in instance.customers if c.id not in seen)
    assert metrics["total_charging_visits"] == sum(s.action.kind == "charge" for s in result.steps)
    for metric, field in (("total_energy_charged", "energy_charged"), ("total_charging_time", "charging_time"),
                          ("total_waiting_time", "waiting_time")):
        assert math.isclose(metrics[metric], sum(getattr(s, field) for s in result.steps), abs_tol=1e-6)
    assert metrics["final_return_feasibility"] is True
    return {"trace_replay": True, "no_future_information": True, "unique_service": True, "safe_returns": True}


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def run_identity(instance_name, instance_hash, scenario_hash, config, code_hash, commit):
    inputs = dict(study=config.get("study", "pilot"), instance=instance_name,
                  instance_sha256=instance_hash, scenario_hash=scenario_hash,
                  scenario_seed=config.get("scenario_seed", 0),
                  algorithm=config.get("algorithm", "COORDINATED_MPC_MCTS"),
                  algorithm_seed=config.get("experiment_seed", 0), requested_config=config,
                  objective_version=OBJECTIVE_VERSION, git_commit=commit, source_sha256=code_hash)
    return {**inputs, "run_id": identifier(inputs)}


def result_sections(payload, identity, scenario=None, instance=None):
    metrics, meta = payload["metrics"], payload["metadata"]
    identity.update(family=meta.get("instance_family"), customer_count=meta.get("number_of_customers"),
                    station_count=meta.get("number_of_stations"))
    payload.update(schema_version=RESULT_SCHEMA_VERSION, identity=identity,
                   scenario=asdict(scenario) if scenario else {},
                   algorithm=payload.get("effective_config", {}))
    sections = {
        "primary": ("complete_service", "customers_served", "customers_unserved", "service_ratio", "vehicles_activated", "total_distance"),
        "secondary": ("total_charging_visits", "total_energy_charged", "total_charging_time", "total_waiting_time", "final_return_feasibility"),
        "coordination": ("decision_epochs", "duplicate_customer_proposal_conflicts", "conflicts_resolved", "mean_unique_intention_coverage", "vehicle_activations_caused_by_coordinator", "wait_selected"),
        "computation": ("mean_planning_time", "median_planning_time", "p95_planning_time", "maximum_planning_time", "total_planning_time", "mcts_iterations", "nodes_expanded"),
        "integrity": ("battery_violations", "capacity_violations", "time_window_violations", "duplicate_service_violations", "hidden_information_violations"),
    }
    if payload["status"] == "completed":
        metrics["complete_service"] = metrics["customers_unserved"] == 0
    for name, keys in sections.items():
        payload[name] = {key: metrics.get(key) for key in keys}
    payload["integrity"]["trace_audit_passed"] = bool(payload.get("audit"))
    payload["scenario"]["scenario_hash"] = identity["scenario_hash"]
    payload["provenance"].update(git_commit=identity["git_commit"],
        timestamp=datetime.now(timezone.utc).isoformat(), machine=platform.machine(),
        processor=platform.processor(), platform=platform.platform(),
        effective_configuration_hash=identifier(payload.get("effective_config", {})),
        requested_configuration_hash=identifier(payload["requested_config"]))


def run_single(instance_name: str, config: dict, output_dir: str | Path | None = None, resume: bool = True) -> Path:
    code_hash = source_fingerprint()
    benchmark_name = instance_name if instance_name.endswith(".txt") else instance_name + ".txt"
    benchmark = BENCHMARK / benchmark_name
    if benchmark.resolve().parent != BENCHMARK.resolve():
        raise ValueError("Only local Schneider instances are supported")
    from hashlib import sha256
    instance_hash = sha256(benchmark.read_bytes()).hexdigest() if benchmark.exists() else None
    commit = git_commit()
    identity = run_identity(instance_name, instance_hash, None, config, code_hash, commit)
    output_dir = Path(output_dir or f"results/raw/{identity['study']}")
    suffix = ".json.gz" if config.get("result_compression") == "gzip" else ".json"
    instance = scenario = None
    original = benchmark_hashes()
    try:
        instance, reference, scenario, scenario_path = prepare(instance_name, config)
        identity = run_identity(instance_name, instance_hash, scenario.identifier, config, code_hash, commit)
        path = output_dir / f"{instance_name}_{identity['algorithm']}_{identity['run_id'][:20]}{suffix}"
        if resume and path.exists():
            existing = load_json(path)
            if existing.get("identity", {}).get("run_id") != identity["run_id"]:
                raise ValueError("Run filename collision with different configuration")
            if existing.get("status") == "completed":
                from .audit import audit_record
                errors = audit_record(existing)
                if errors:
                    raise ValueError("Existing run failed audit: " + "; ".join(errors))
                return path
        if config.get("algorithm") == "ORACLE_REFERENCE":
            from .oracle import oracle_reference
            result = oracle_reference(instance, reference, scenario, config)
        elif config.get("algorithm") == "STATIC_REFERENCE":
            result = static_reference_result(instance, reference, scenario, config)
        else:
            result = EventDrivenSimulator(instance, scenario, simulation_config(config)).run()
        audit = audit_result(result, instance, scenario)
        if benchmark_hashes() != original:
            raise RuntimeError("Benchmark bytes changed during experiment")
        payload = {**asdict(result), "status": "completed", "audit": audit,
                   "requested_config": config, "scenario_path": str(scenario_path),
                   "provenance": {"source_sha256": code_hash, "python": platform.python_version(),
                                  "packages": {p: version(p) for p in ("numpy", "scipy", "pandas", "matplotlib", "PyYAML")}}}
    except Exception as error:
        payload = {"status": "failed", "metadata": {"instance": instance_name,
                   "algorithm": config.get("algorithm", "COORDINATED_MPC_MCTS"),
                   "scenario_seed": config.get("scenario_seed", 0), "algorithm_seed": config.get("experiment_seed", 0),
                   "DoD_target": config.get("dynamicity", 0.5)}, "requested_config": config,
                   "metrics": {"feasible": False}, "error": str(error), "traceback": traceback.format_exc(),
                   "provenance": {"source_sha256": code_hash, "python": platform.python_version(),
                                  "packages": {p: version(p) for p in ("numpy", "scipy", "pandas", "matplotlib", "PyYAML")}}}
    result_sections(payload, identity, scenario, instance)
    path = output_dir / f"{instance_name}_{identity['algorithm']}_{identity['run_id'][:20]}{suffix}"
    if path.exists():
        existing = load_json(path)
        if existing.get("identity", {}).get("run_id") != identity["run_id"]:
            raise ValueError("Refusing to overwrite a different run")
    save_json(path, payload)
    return path


def grid_cases(config: dict, ablations: bool = False):
    instances = config.get("instances", sorted(p.stem for p in BENCHMARK.glob("*_21.txt")))
    base = {k: v for k, v in config.items() if k not in {"instances", "grid", "ablations"}}
    grid = dict(config.get("grid", {}))
    names = list(grid)
    variants = [dict(zip(names, values)) for values in product(*(grid[n] for n in names))]
    if ablations:
        variants = [{}]
        for name, values in config.get("ablations", {}).items():
            variants.extend({name: value, "ablation_factor": name} for value in values)
    seen = set()
    for instance, changes in product(instances, variants):
        effective = {**base, **changes}
        key = identifier((instance, effective))
        if key in seen:
            continue
        seen.add(key)
        yield instance, effective


def run_grid(config: dict, output_dir=None, ablations: bool = False, execute=False):
    if config.get("study") == "main":
        raise RuntimeError("Main grid execution is disabled. Use evrp.cli paper with its calibration/runtime gate")
    from .paper import estimate
    estimation = estimate(config, output_dir)
    print(json.dumps(estimation, indent=2), flush=True)
    duration = estimation["estimated_sequential_seconds"]
    if not execute and (duration is None or duration > config.get("confirmation_hours", 6)*3600):
        raise RuntimeError("Unknown or long campaign runtime; explicit --execute is required")
    if config.get("study") == "main":
        from .validation import require_reference_validation
        require_reference_validation()
        if "STATIC_REFERENCE" in config.get("grid", {}).get("algorithm", []):
            raise ValueError("STATIC_REFERENCE is not an online main-study competitor")
    for instance, effective in grid_cases(config, ablations):
        yield run_single(instance, effective, output_dir)

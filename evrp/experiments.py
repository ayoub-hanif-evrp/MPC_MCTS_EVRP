"""Resumable, provenance-bound research runs and YAML configuration loading."""

from dataclasses import asdict, replace
from importlib.metadata import version
from itertools import product
from pathlib import Path
import json
import platform
import traceback

import yaml

from .instance import load_instance
from .mpc import MPCConfig
from .reference import ReferenceConfig, ReferenceSchedule, solve_reference
from .scenario import DynamicScenario, generate
from .simulator import EventDrivenSimulator, ExperimentResult, SimulationConfig, SimulationEvent
from .storage import BENCHMARK, ROOT, benchmark_hashes, identifier, save_json


def load_config(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a YAML mapping")
    return data


def simulation_config(config: dict) -> SimulationConfig:
    mapping = {"prediction_horizon": "prediction_horizon", "control_horizon": "control_horizon",
               "top_L": "top_l", "candidate_limit": "candidate_limit", "mcts_iterations": "iterations",
               "uct_c": "uct_c", "budget_mode": "budget_mode", "mcts_time_limit": "time_limit",
               "charging_mode": "charging_mode", "charge_fractions": "charge_fractions"}
    kwargs = {target: config[source] for source, target in mapping.items() if source in config}
    if "charge_fractions" in kwargs:
        kwargs["charge_fractions"] = tuple(kwargs["charge_fractions"])
    return SimulationConfig(algorithm=config.get("algorithm", "COORDINATED_MPC_MCTS"),
                            experiment_seed=config.get("experiment_seed", 0),
                            parallel_agents=config.get("parallel_agents", False),
                            workers=config.get("workers", 2), mpc=MPCConfig(**kwargs))


def source_fingerprint() -> str:
    return identifier({p.name: p.read_text(encoding="utf-8") for p in sorted((ROOT / "evrp").glob("*.py"))})


def prepare(instance_name: str, config: dict):
    path = BENCHMARK / (instance_name if instance_name.endswith(".txt") else instance_name + ".txt")
    if path.resolve().parent != BENCHMARK.resolve():
        raise ValueError("Only the repository Schneider benchmark is supported")
    instance = load_instance(path)
    ref_config = ReferenceConfig(config.get("reference_solver_multistarts", 3),
                                 config.get("reference_improvement_passes", 1),
                                 config.get("reference_seed", 0))
    key = identifier({"instance": instance.sha256, "config": asdict(ref_config), "generator_version": 1})[:16]
    ref_path = ROOT / "data" / "reference_schedules" / f"{instance.name}_{key}.json"
    if ref_path.exists():
        reference = ReferenceSchedule.load(ref_path, instance)
    else:
        reference = solve_reference(instance, ref_config)
        reference.save(ref_path)
    if config.get("scenario_path"):
        scenario = DynamicScenario.load(config["scenario_path"], instance)
        if scenario.reference_schedule_identifier != reference.identifier or scenario.fleet_size != reference.fleet_size:
            raise ValueError("Scenario must use the selected reference schedule and its fleet size")
    else:
        scenario = generate(instance, reference, config.get("scenario_seed", 0), config.get("dynamicity", 0.5),
                            config.get("dynamic_selection_mode", "exact_count"))
    scenario_path = ROOT / "data" / "generated_scenarios" / f"{instance.name}_{scenario.identifier[:16]}.json"
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
    states = {k: initial_vehicle(instance, k) for k in range(scenario.fleet_size)}
    seen = set()
    for step in sorted(result.steps, key=lambda s: (s.before.time, s.before.id)):
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
    for decision in result.decisions:
        assert all(releases[key] <= decision["time"] for key in decision["available"])
        for plan in decision["plans"].values():
            for action in plan["actions"]:
                if action["kind"] == "serve":
                    assert action["destination"] in decision["available"], "Hidden or committed customer in predicted tail"
    assert all(s.location == instance.infrastructure.depot and s.finished and s.time <= instance.infrastructure.depot.due + EPS
               for s in states.values()), "Vehicle did not return safely"
    assert len(seen) == result.metrics["customers_served"]
    return {"trace_replay": True, "no_future_information": True, "unique_service": True, "safe_returns": True}


def run_single(instance_name: str, config: dict, output_dir: str | Path = "results/runs", resume: bool = True) -> Path:
    code_hash = source_fingerprint()
    benchmark_name = instance_name if instance_name.endswith(".txt") else instance_name + ".txt"
    benchmark = BENCHMARK / benchmark_name
    if benchmark.resolve().parent != BENCHMARK.resolve():
        raise ValueError("Only local Schneider instances are supported")
    from hashlib import sha256
    instance_hash = sha256(benchmark.read_bytes()).hexdigest() if benchmark.exists() else None
    key = identifier({"instance": instance_name, "instance_sha256": instance_hash,
                      "config": config, "source": code_hash})[:20]
    path = Path(output_dir) / f"{instance_name}_{config.get('algorithm', 'COORDINATED_MPC_MCTS')}_{key}.json"
    if resume and path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("status") == "completed":
            return path
    original = benchmark_hashes()
    try:
        instance, reference, scenario, scenario_path = prepare(instance_name, config)
        if config.get("algorithm") == "STATIC_REFERENCE":
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
                   "provenance": {"source_sha256": code_hash}}
    save_json(path, payload)
    return path


def run_grid(config: dict, output_dir="results/runs", ablations: bool = False):
    instances = config.get("instances", sorted(p.stem for p in BENCHMARK.glob("*_21.txt")))
    base = {k: v for k, v in config.items() if k not in {"instances", "grid", "ablations"}}
    grid = dict(config.get("grid", {}))
    names = list(grid)
    variants = [dict(zip(names, values)) for values in product(*(grid[n] for n in names))]
    if ablations:
        variants = [{}]
        for name, values in config.get("ablations", {}).items():
            variants.extend({name: value} for value in values)
    seen = set()
    for instance, changes in product(instances, variants):
        effective = {**base, **changes}
        key = identifier((instance, effective))
        if key in seen:
            continue
        seen.add(key)
        yield run_single(instance, effective, output_dir)

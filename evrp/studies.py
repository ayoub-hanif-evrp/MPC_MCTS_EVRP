"""Provenance-bound study plans and service-first screening gates.

prepare(name, config) returns (instance, reference, scenario, path); run_single
returns a result file. New caches are confined to repository results/.
Matched algorithms receive the same prepared scenario_path.
"""

from hashlib import sha256
from itertools import product
import math
from pathlib import Path
import random
import statistics

from .experiments import prepare, run_single, source_fingerprint
from .storage import BENCHMARK, ROOT, identifier, load_json, save_json

SCREEN_INSTANCES = ("c101_21", "c201_21", "r101_21", "r201_21", "rc101_21", "rc201_21")
ALGORITHMS = ("RH_REGRET", "INDEPENDENT_MPC_MCTS", "COORDINATED_MPC_MCTS")
GATED_STUDIES = {"main", "ablations", "realtime"}
DEFAULTS = dict(fleet_mode="fixed_reference", prediction_horizon=5, control_horizon=1,
                mcts_iterations=32, top_L=3, candidate_limit=12, station_candidate_limit=4,
                charge_target_limit=5, charging_mode="partial", route_continuity=True,
                regret_repair=True, proposal_selection="quality", dynamic_selection_mode="exact_count",
                parallel_agents=False, workers=1, trace_level="summary", budget_mode="iterations",
                experiment_seed=0, scenario_seed=0, dynamicity=0.5, max_idle_wait=0,
                algorithm="COORDINATED_MPC_MCTS", reference_solver_multistarts=3,
                reference_improvement_passes=1, reference_seed=0, reference_label_limit=24,
                require_root_coverage=True, diagnostics=True)
STRUCTURE = {"study", "instances", "grid", "variants", "gate", "stage1", "stage2"}
# Declared before execution, saved with the protocol and bound into gate evidence.
GATE_POLICY = dict(bootstrap_samples=2000, bootstrap_seed=0, min_improving_pairs=2,
                   min_improving_families=2, max_p95_planning_seconds=5.0)


def result_path(path):
    """Reject traversal and symlink/junction escapes, including non-existing paths."""
    path = Path(path)
    resolved = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    allowed = (ROOT / "results").resolve()
    if not allowed.is_relative_to(ROOT.resolve()) or not resolved.is_relative_to(allowed):
        raise ValueError("All study outputs must stay inside the repository results/ directory")
    return resolved


def runtime_config(config):
    effective = {**DEFAULTS, **{k: v for k, v in config.items() if k not in STRUCTURE or k == "study"}}
    if effective["fleet_mode"] != "fixed_reference":
        raise ValueError("The final-paper track requires a fixed_reference fleet")
    return effective


def _screen_config(config):
    effective = runtime_config(config)
    for key in ("fleet_mode", "prediction_horizon", "control_horizon", "mcts_iterations", "top_L",
                "charging_mode", "route_continuity", "regret_repair", "proposal_selection",
                "dynamic_selection_mode", "parallel_agents", "budget_mode", "experiment_seed", "max_idle_wait",
                "require_root_coverage", "candidate_limit", "station_candidate_limit", "charge_target_limit"):
        if effective[key] != DEFAULTS[key]:
            raise ValueError(f"Screening requires {key}={DEFAULTS[key]!r}")
    if tuple(config.get("instances", SCREEN_INSTANCES)) != SCREEN_INSTANCES:
        raise ValueError("Screening requires exactly the six prescribed 100-customer instances")
    if any(key in config for key in ("grid", "variants", "stage1", "stage2", "scenario_path")):
        raise ValueError("The two screening stages are fixed; grid/scenario overrides are forbidden")
    policy = {**GATE_POLICY, **config.get("gate", {})}
    if set(policy) != set(GATE_POLICY):
        raise ValueError("Unknown screening gate setting")
    for key in ("bootstrap_samples", "min_improving_pairs", "min_improving_families"):
        if type(policy[key]) is not int or policy[key] < (100 if key == "bootstrap_samples" else 2):
            raise ValueError(f"Invalid gate threshold: {key}")
    if type(policy["bootstrap_seed"]) is not int or not math.isfinite(policy["max_p95_planning_seconds"]) or policy["max_p95_planning_seconds"] <= 0:
        raise ValueError("Invalid bootstrap seed or planning-time threshold")
    return effective, policy


def plan_study(study, config):
    """Pure planning: never prepares references/scenarios or launches runs."""
    base = runtime_config(config)
    if study in {"stage1", "stage2"}:
        _screen_config(config)
        dods, seeds = ((0.0, 0.5), (0,)) if study == "stage1" else ((0.25, 0.5, 0.75), (0, 1))
        return [(name, {**base, "study": f"screening_{study}", "dynamicity": dod,
                        "scenario_seed": seed, "algorithm": algorithm})
                for name, dod, seed, algorithm in product(SCREEN_INSTANCES, dods, seeds, ALGORITHMS)]
    if study not in GATED_STUDIES | {"smoke"}:
        raise ValueError(f"Unknown study: {study}")
    instances = config.get("instances", [])
    if not instances or len(set(instances)) != len(instances):
        raise ValueError("Study needs a nonempty unique instance list")
    grid = config.get("grid", {})
    allowed_axes = {"dynamicity", "scenario_seed", "experiment_seed", "algorithm", "mcts_time_limit"}
    if set(grid) - allowed_axes or any(not isinstance(v, list) or not v for v in grid.values()):
        raise ValueError("Invalid study grid")
    if "variants" in config and study != "ablations":
        raise ValueError("Variants are reserved for the ablation study")
    variants = config.get("variants", [{"name": "baseline"}])
    if not variants or len({v["name"] for v in variants}) != len(variants):
        raise ValueError("Ablation variants must have unique names")
    result, seen = [], set()
    for name, values, variant in product(instances, product(*grid.values()), variants):
        changes = {k: v for k, v in variant.items() if k != "name"}
        if len(changes) > 1 or set(changes) - {"algorithm", "route_continuity", "regret_repair", "prediction_horizon", "top_L", "proposal_selection"}:
            raise ValueError("Ablations must change one supported factor at a time")
        effective = {**base, **dict(zip(grid, values)), **changes, "study": study}
        if study == "ablations":
            effective["ablation_factor"] = variant["name"]
        if effective["algorithm"] not in (*ALGORITHMS, "GREEDY", "MPC_MCTS_H1"):
            raise ValueError("Unknown final-paper algorithm")
        if effective["algorithm"] == "MPC_MCTS_H1" and study != "ablations":
            raise ValueError("MPC_MCTS_H1 is only an ablation")
        if study == "realtime":
            if effective["parallel_agents"] or effective["workers"] != 1 or effective.get("outer_workers", 1) != 1:
                raise ValueError("Realtime must run in isolation with one worker")
            if effective["budget_mode"] != "wall_clock" or effective["require_root_coverage"]:
                raise ValueError("Realtime requires wall_clock with require_root_coverage=false")
            if effective.get("mcts_time_limit") not in (0.05, 0.10, 0.25, 0.50):
                raise ValueError("Realtime requires a prescribed small deadline")
        if study == "main" and effective["dynamicity"] == 0:
            raise ValueError("Static sanity checks belong to screening, not main")
        key = identifier((name, effective))
        if key in seen:
            raise ValueError("Duplicate study condition")
        seen.add(key)
        result.append((name, effective))
    return result


def _file_hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def _binding(config):
    names = sorted(set(SCREEN_INSTANCES) | set(config.get("instances", [])))
    return dict(config=config, config_sha256=identifier(config), source_sha256=source_fingerprint(),
                benchmarks={name: _file_hash(BENCHMARK / f"{name}.txt") for name in names})


def _condition(name, config):
    return (name, config["dynamicity"], config["scenario_seed"])


def _run_phase(study, config, output, binding=None):
    output = result_path(output)
    plan = plan_study(study, config)
    manifest = dict(study=study, binding=binding or _binding(config), planned_runs=len(plan),
                    status="RUNNING", scenarios=[], runs=[])
    manifest_path = output / "manifest.json"
    save_json(manifest_path, manifest)
    groups = {}
    for name, effective in plan:
        groups.setdefault(_condition(name, effective), []).append(effective)
    for (name, dod, seed), variants in groups.items():
        instance, reference, scenario, scenario_path = prepare(name, variants[0])
        scenario_path = result_path(scenario_path)
        if (scenario.target_DoD != dod or scenario.scenario_seed != seed or
                scenario.fleet_size != reference.fleet_size or
                scenario.reference_schedule_identifier != reference.identifier):
            raise ValueError("Prepared scenario differs from its matched reference/condition")
        eligible = math.isclose(scenario.realized_DoD, dod, rel_tol=0, abs_tol=1e-12)
        item = dict(instance=name, dynamicity=dod, scenario_seed=seed,
                    instance_sha256=instance.sha256, customer_count=len(instance.customers),
                    scenario_path=str(scenario_path), scenario_sha256=_file_hash(scenario_path),
                    scenario_identifier=scenario.identifier, reference_identifier=reference.identifier,
                    fleet_size=reference.fleet_size, target_DoD=scenario.target_DoD,
                    realized_DoD=scenario.realized_DoD, eligible=eligible,
                    reason=None if eligible else "Requested DoD was not achieved")
        manifest["scenarios"].append(item)
        # Stage 1 always executes all 36 conditions and discloses achieved DoD.
        if eligible or study in {"stage1", "smoke"}:
            for effective in variants:
                requested = {**effective, "scenario_path": str(scenario_path)}
                path = result_path(run_single(name, requested, output / "runs"))
                manifest["runs"].append(dict(path=str(path), sha256=_file_hash(path),
                                             instance=name, requested_config=requested))
                save_json(manifest_path, manifest)
                record = load_json(path)
                if record["status"] != "completed":
                    manifest["status"] = "FAILED"
                    save_json(manifest_path, manifest)
                    raise RuntimeError(f"{name} {effective['algorithm']}: {record.get('error')}")
                metrics = record["metrics"]
                print(f"{study} {len(manifest['runs'])}/{len(plan)} {name} DoD={dod:g} "
                      f"{effective['algorithm']} served={metrics['customers_served']} "
                      f"EVs={metrics['vehicles_activated']} planning={metrics.get('total_planning_time', 0):.2f}s", flush=True)
        save_json(manifest_path, manifest)
    if manifest["binding"] != _binding(config):
        raise RuntimeError("Source/config/benchmark changed during execution; gate remains blocked")
    manifest["status"] = "COMPLETED"
    save_json(manifest_path, manifest)
    return manifest


def _verified_records(manifest, config, study):
    """Reconstruct the plan, verify evidence files, then independently audit runs."""
    from .audit import audit_record

    if manifest.get("status") != "COMPLETED" or manifest.get("binding") != _binding(config) or manifest.get("study") != study:
        raise ValueError("Missing or stale study provenance; rerun screening")
    plan = plan_study(study, config)
    if manifest.get("planned_runs") != len(plan):
        raise ValueError("Study plan count mismatch")
    groups = {_condition(name, effective) for name, effective in plan}
    scenarios = {}
    for item in manifest["scenarios"]:
        key = (item["instance"], item["dynamicity"], item["scenario_seed"])
        if key in scenarios:
            raise ValueError("Duplicate scenario evidence")
        path = result_path(item["scenario_path"])
        if _file_hash(path) != item["scenario_sha256"]:
            raise ValueError("Scenario evidence changed")
        raw = load_json(path)
        if identifier(raw) != item["scenario_identifier"]:
            raise ValueError("Scenario identifier mismatch")
        for field, expected in (("target_DoD", item["dynamicity"]), ("realized_DoD", item["realized_DoD"]),
                                ("scenario_seed", item["scenario_seed"]), ("fleet_size", item["fleet_size"]),
                                ("instance_sha256", item["instance_sha256"]),
                                ("reference_schedule_identifier", item["reference_identifier"])):
            if raw.get(field) != expected:
                raise ValueError("Scenario metadata mismatch")
        if item["instance_sha256"] != manifest["binding"]["benchmarks"][item["instance"]]:
            raise ValueError("Scenario benchmark mismatch")
        achieved = math.isclose(item["dynamicity"], item["realized_DoD"], rel_tol=0, abs_tol=1e-12)
        if item["eligible"] != achieved:
            raise ValueError("Scenario eligibility mismatch")
        if study in {"stage1", "stage2"} and item["customer_count"] != 100:
            raise ValueError("Screening requires 100-customer instances")
        scenarios[key] = item
    if set(scenarios) != groups:
        raise ValueError("Missing or unexpected scenario conditions")
    expected = {}
    for name, effective in plan:
        item = scenarios[_condition(name, effective)]
        if item["eligible"] or study in {"stage1", "smoke"}:
            requested = {**effective, "scenario_path": item["scenario_path"]}
            expected[identifier((name, requested))] = item
    records, seen = [], set()
    for entry in manifest["runs"]:
        key = identifier((entry["instance"], entry["requested_config"]))
        if key not in expected or key in seen:
            raise ValueError("Unexpected or duplicate run evidence")
        seen.add(key)
        path = result_path(entry["path"])
        if _file_hash(path) != entry["sha256"]:
            raise ValueError("Result evidence changed")
        record = load_json(path)
        item = expected[key]
        if (record.get("requested_config") != entry["requested_config"] or
                record.get("provenance", {}).get("source_sha256") != manifest["binding"]["source_sha256"] or
                record.get("identity", {}).get("scenario_hash") != item["scenario_identifier"]):
            raise ValueError("Run source/config/scenario provenance mismatch")
        if record.get("status") != "completed":
            raise ValueError("Failed run blocks the study gate")
        errors = audit_record(record)
        if errors:
            raise ValueError("Run audit failed: " + "; ".join(errors))
        records.append(record)
    if seen != set(expected):
        raise ValueError("Missing run evidence")
    return records


def paired_statistics(differences, *, samples=2000, seed=0):
    values = sorted(float(v) for v in differences)
    if any(not math.isfinite(v) for v in values) or samples < 1:
        raise ValueError("Paired statistics require finite values and positive bootstrap samples")
    n = len(values)
    result = dict(n=n, wins=sum(v < -1e-9 for v in values), ties=sum(abs(v) <= 1e-9 for v in values),
                  losses=sum(v > 1e-9 for v in values), mean=statistics.mean(values) if n else None,
                  median=statistics.median(values) if n else None, ci95=[None, None])
    if n >= 2:
        rng = random.Random(seed)
        means = sorted(statistics.mean(rng.choices(values, k=n)) for _ in range(samples))
        def quantile(q):
            position = (len(means) - 1) * q
            lo, hi = math.floor(position), math.ceil(position)
            return means[lo] + (means[hi] - means[lo]) * (position - lo)
        result["ci95"] = [quantile(0.025), quantile(0.975)]
    return result


def stage1_gate(records):
    reasons, detail = [], {}
    expected = set(product(SCREEN_INSTANCES, (0.0, 0.5), ALGORITHMS))
    seen = set()
    for record in records:
        meta, metrics = record["metadata"], record["metrics"]
        key = (meta["instance"], meta["DoD_target"], meta["algorithm"])
        if key in seen or key not in expected or meta["scenario_seed"] != 0 or meta["algorithm_seed"] != 0:
            reasons.append("Unexpected/duplicate Stage-1 condition")
        seen.add(key)
        if record["status"] != "completed" or not metrics.get("final_return_feasibility", False):
            reasons.append("Stage-1 run failed or did not return safely")
    if seen != expected or len(records) != 36:
        reasons.append("Stage 1 requires exactly 36 matched runs")
    for algorithm in ALGORITHMS:
        static = [r["metrics"] for r in records if r["metadata"]["algorithm"] == algorithm and r["metadata"]["DoD_target"] == 0]
        dynamic = [r["metrics"] for r in records if r["metadata"]["algorithm"] == algorithm and r["metadata"]["DoD_target"] == 0.5]
        ratio = statistics.mean(m["service_ratio"] for m in dynamic) if dynamic else 0
        detail[algorithm] = dict(static_complete=sum(m["customers_unserved"] == 0 for m in static),
                                 dynamic_complete=sum(m["customers_unserved"] == 0 for m in dynamic),
                                 dynamic_mean_service=ratio)
    coordinated = detail[ALGORITHMS[2]]
    if coordinated["static_complete"] != 6:
        reasons.append("Coordinated static service must be complete on all six instances")
    if coordinated["dynamic_mean_service"] < 0.98 - 1e-12:
        reasons.append("Coordinated dynamic mean service is below 98%")
    if coordinated["dynamic_complete"] < 5:
        reasons.append("Coordinated dynamic service must be complete on at least five instances")
    return dict(status="FAIL" if reasons else "PASS", reasons=sorted(set(reasons)), algorithms=detail)


def screening_gate(records, policy=None):
    policy = {**GATE_POLICY, **(policy or {})}
    groups, reasons, comparisons = {}, [], {}
    for record in records:
        meta = record["metadata"]
        key = (meta["instance"], meta["DoD_target"], meta["scenario_seed"], meta["algorithm_seed"], meta["scenario_identifier"])
        group = groups.setdefault(key, {})
        if meta["algorithm"] in group or record["status"] != "completed":
            reasons.append("Duplicate or failed paired run")
        group[meta["algorithm"]] = record["metrics"]
    if not groups or any(set(group) != set(ALGORITHMS) for group in groups.values()):
        return dict(status="FAIL", reasons=["Missing matched algorithm triplets"], comparisons={})
    for baseline in ALGORITHMS[:2]:
        differences = {metric: [] for metric in ("customers_unserved", "vehicles_activated", "total_distance")}
        improvements, families = 0, set()
        for key, group in sorted(groups.items()):
            coordinated, other = group[ALGORITHMS[2]], group[baseline]
            du = coordinated["customers_unserved"] - other["customers_unserved"]
            dv = coordinated["vehicles_activated"] - other["vehicles_activated"]
            differences["customers_unserved"].append(du)
            if du == 0:
                differences["vehicles_activated"].append(dv)
                if dv == 0:
                    differences["total_distance"].append(coordinated["total_distance"] - other["total_distance"])
            if du < 0 or (du == 0 and dv < 0):
                improvements += 1
                families.add("RC" if key[0].startswith("rc") else "R" if key[0].startswith("r") else "C")
        stats = {metric: paired_statistics(values, samples=policy["bootstrap_samples"], seed=policy["bootstrap_seed"])
                 for metric, values in differences.items()}
        comparisons[baseline] = dict(metrics=stats, improving_pairs=improvements, improving_families=sorted(families))
        service = stats["customers_unserved"]
        if service["mean"] > 1e-9 or service["losses"] > service["wins"]:
            reasons.append(f"Service systematically worse than {baseline}")
        if improvements < policy["min_improving_pairs"] or len(families) < policy["min_improving_families"]:
            reasons.append(f"Insufficient service/conditional-EV improvements across families versus {baseline}")
    p95 = [group[ALGORITHMS[2]].get("p95_planning_time") for group in groups.values()]
    if any(v is None or not math.isfinite(v) or v < 0 or v > policy["max_p95_planning_seconds"] for v in p95):
        reasons.append("Coordinated planning exceeds the declared p95 limit or lacks timing evidence")
    return dict(status="FAIL" if reasons else "PASS", reasons=sorted(set(reasons)),
                comparisons=comparisons, policy=policy, paired_scenarios=len(groups))


def _write_gate(output, gate):
    output = result_path(output)
    save_json(output / "GATE.json", gate)
    lines = ["# Screening Gate", "", f"GATE = {gate['status']}", "",
             "Differences are coordinated minus baseline; negative is better.",
             "EV comparisons require equal service; distance requires equal service and EVs.",
             "Intervals are deterministic percentile paired-bootstrap CIs for mean differences.",
             "Stage 1: coordinated static 6/6 complete, dynamic mean >=98%, dynamic >=5/6 complete.", ""]
    if gate.get("error"):
        lines += [f"Error: {gate['error']}", ""]
    for stage in ("stage1", "stage2"):
        value = gate.get(stage, {})
        lines += [f"## {stage}", "", f"Status: {value.get('status', 'NOT RUN')}", ""]
        lines += [f"- {reason}" for reason in value.get("reasons", [])]
        if value.get("algorithms"):
            lines += ["", "| Algorithm | Static complete /6 | Dynamic complete /6 | Dynamic mean service |", "|---|---:|---:|---:|"]
            for algorithm, metrics in value["algorithms"].items():
                lines.append(f"| {algorithm} | {metrics['static_complete']} | {metrics['dynamic_complete']} | {metrics['dynamic_mean_service']:.3f} |")
        for baseline, comparison in value.get("comparisons", {}).items():
            lines += ["", f"### Versus {baseline}", "", "| Metric | n | Wins | Ties | Losses | Mean | Median | 95% CI |", "|---|---:|---:|---:|---:|---:|---:|---|"]
            for metric, stats in comparison["metrics"].items():
                lines.append(f"| {metric} | {stats['n']} | {stats['wins']} | {stats['ties']} | {stats['losses']} | {stats['mean']} | {stats['median']} | {stats['ci95']} |")
            lines += ["", f"Improving pairs: {comparison['improving_pairs']}; families: {', '.join(comparison['improving_families'])}."]
    lines += ["", "## Eligibility", "", "Ineligible scenarios remain in manifests and are excluded from Stage 2.", ""]
    for item in gate.get("ineligible", []):
        lines.append(f"- {item['stage']}: {item['instance']}, seed {item['scenario_seed']}, target DoD {item['target_DoD']}, realized DoD {item['realized_DoD']}")
    lines += ["", "No main, ablation, or realtime study is launched by screening.", ""]
    (output / "GATE.md").write_text("\n".join(lines), encoding="utf-8")


def run_screening(config, output="results/screening", *, stage="all"):
    if stage not in {"1", "2", "all"}:
        raise ValueError("Unknown screening stage")
    _, policy = _screen_config(config)
    output = result_path(output)
    binding = _binding(config)
    gate = dict(status="BLOCKED", binding=binding)
    _write_gate(output, gate)
    try:
        first = (_run_phase("stage1", config, output / "stage1", binding) if stage != "2"
                 else load_json(output / "stage1/manifest.json"))
        gate["stage1"] = stage1_gate(_verified_records(first, config, "stage1"))
        gate["stage1_manifest_sha256"] = _file_hash(output / "stage1/manifest.json")
        gate["ineligible"] = [{"stage": "stage1", **s} for s in first["scenarios"] if not s["eligible"]]
        if gate["stage1"]["status"] != "PASS":
            gate["status"] = "FAIL"
        elif stage != "1":
            second = _run_phase("stage2", config, output / "stage2", binding)
            gate["stage2"] = screening_gate(_verified_records(second, config, "stage2"), policy)
            gate["stage2_manifest_sha256"] = _file_hash(output / "stage2/manifest.json")
            gate["ineligible"] += [{"stage": "stage2", **s} for s in second["scenarios"] if not s["eligible"]]
            gate["status"] = gate["stage2"]["status"]
        _write_gate(output, gate)
        return gate
    except (ValueError, RuntimeError, OSError) as error:
        gate.update(status="FAIL", error=str(error))
        _write_gate(output, gate)
        raise


def require_screening_pass(config, output="results/screening"):
    _, policy = _screen_config(config)
    output = result_path(output)
    gate = load_json(output / "GATE.json")
    if gate.get("status") != "PASS" or gate.get("binding") != _binding(config):
        raise ValueError("A fresh screening PASS for the current source/config/benchmarks is required")
    for study in ("stage1", "stage2"):
        path = output / study / "manifest.json"
        if _file_hash(path) != gate.get(f"{study}_manifest_sha256"):
            raise ValueError("Screening manifest changed since the gate")
        records = _verified_records(load_json(path), config, study)
        decision = stage1_gate(records) if study == "stage1" else screening_gate(records, policy)
        if decision != gate.get(study) or decision["status"] != "PASS":
            raise ValueError("Screening evidence no longer supports PASS")
    return gate


def _compatible(config, screening_config, study):
    current, screened = runtime_config(config), runtime_config(screening_config)
    allowed = {"study", "dynamicity", "scenario_seed", "algorithm", "experiment_seed"}
    if study == "realtime":
        allowed |= {"budget_mode", "mcts_time_limit", "execution_profile", "outer_workers", "require_root_coverage"}
    differences = {k for k in set(current) | set(screened) if k not in allowed and current.get(k) != screened.get(k)}
    if differences:
        raise ValueError("Study differs from screened scientific configuration: " + ", ".join(sorted(differences)))


def run_study(study, config, output, *, execute=False, screening="results/screening", screening_config=None):
    output = result_path(output)
    plan = plan_study(study, config)
    if not execute:
        return dict(status="PLANNED", study=study, planned_runs=len(plan), output=str(output),
                    message="No experiments launched. Execution requires --execute and a fresh screening PASS.")
    if study in GATED_STUDIES:
        if screening_config is None:
            raise ValueError("Current screening configuration is required")
        _compatible(config, screening_config, study)
        require_screening_pass(screening_config, screening)
    manifest = _run_phase(study, config, output)
    failures = sum(load_json(entry["path"])["status"] != "completed" for entry in manifest["runs"])
    return dict(status="failed" if failures else "completed", study=study, planned_runs=len(plan),
                executed_runs=len(manifest["runs"]), failed_runs=failures,
                ineligible_scenarios=sum(not s["eligible"] for s in manifest["scenarios"]),
                manifest=str(output / "manifest.json"))

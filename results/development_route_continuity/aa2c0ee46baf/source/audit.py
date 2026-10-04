"""Independent disk-record audits before scientific aggregation."""

from dataclasses import asdict, replace
from pathlib import Path
import json
import math
from collections import Counter

import pandas as pd

from .instance import Location, load_instance
from .model import Action, Transition, VehicleState
from .reference import ReferenceConfig, ReferenceSchedule
from .scenario import DynamicScenario
from .simulator import ExperimentResult, SimulationEvent
from .storage import BENCHMARK, ROOT, identifier, writable_path, load_json
from .versions import OBJECTIVE_VERSION, REFERENCE_SOLVER_VERSION, RESULT_SCHEMA_VERSION


def result_files(directory):
    return [p for p in sorted([*Path(directory).rglob("*.json"), *Path(directory).rglob("*.json.gz")])
            if not any(part.startswith("archive") for part in p.parts)]


def decode_result(raw):
    def vehicle(data):
        data = dict(data)
        data["location"] = Location(**data["location"])
        for key in ("route_history", "served_customers"):
            data[key] = tuple(data[key])
        if data["current_committed_action"]:
            data["current_committed_action"] = Action(**data["current_committed_action"])
        return VehicleState(**data)
    steps = [Transition(**{**s, "before": vehicle(s["before"]), "after": vehicle(s["after"]),
                           "action": Action(**s["action"])}) for s in raw["steps"]]
    events = [SimulationEvent(**{**e, "action": Action(**e["action"]) if e["action"] else None})
              for e in raw["events"]]
    return ExperimentResult(raw["metadata"], raw["effective_config"], raw["metrics"], events,
                            steps, raw["decisions"], raw["searches"], raw["unserved_customers"], raw.get("diagnostics", {}))


def audit_record(record):
    errors = []
    def check(condition, message):
        if not condition:
            errors.append(message)
    try:
        required = {"identity", "scenario", "algorithm", "primary", "secondary", "coordination",
                    "computation", "integrity", "provenance", "requested_config", "metadata", "metrics"}
        check(required.issubset(record), "missing schema sections")
        check(record.get("schema_version") == RESULT_SCHEMA_VERSION, "stale result schema")
        if errors:
            return errors
        ident, provenance, config = record["identity"], record["provenance"], record["requested_config"]
        from .experiments import audit_result, run_identity, simulation_config
        expected = run_identity(ident["instance"], ident["instance_sha256"], ident["scenario_hash"],
                                config, provenance["source_sha256"], provenance["git_commit"])
        check(all(ident.get(k) == v for k, v in expected.items()), "run ID or identity/config mismatch")
        check(ident["objective_version"] == OBJECTIVE_VERSION, "stale objective version")
        check(provenance["requested_configuration_hash"] == identifier(config), "requested configuration mismatch")
        check(provenance["effective_configuration_hash"] == identifier(record.get("effective_config", {})),
              "effective configuration hash mismatch")
        check(all(k in provenance for k in ("python", "packages", "timestamp", "machine")), "missing provenance")
        if record["status"] == "failed":
            return errors
        check(record["status"] == "completed", "unknown run status")
        instance = load_instance(BENCHMARK / (ident["instance"] + ".txt"))
        check(instance.sha256 == ident["instance_sha256"], "stale base instance hash")
        meta = record["metadata"]
        for key in ("instance", "instance_sha256", "algorithm", "algorithm_seed", "scenario_seed"):
            check(meta.get(key) == ident.get(key), f"metadata identity mismatch: {key}")
        check(meta.get("number_of_customers") == len(instance.customers) == ident.get("customer_count"), "customer count mismatch")
        check(meta.get("number_of_stations") == len(instance.infrastructure.stations) == ident.get("station_count"), "station count mismatch")
        check(meta.get("instance_family") == ident.get("family"), "instance family mismatch")
        scenario = DynamicScenario.load(record["scenario_path"], instance)
        check(scenario.identifier == ident["scenario_hash"], "stale scenario hash")
        check(meta.get("scenario_identifier") == scenario.identifier, "metadata scenario mismatch")
        check(meta.get("reference_schedule_identifier") == scenario.reference_schedule_hash, "metadata reference mismatch")
        check(meta.get("DoD_target") == scenario.target_DoD and meta.get("DoD_realized") == scenario.realized_DoD,
              "metadata dynamicity mismatch")
        check(scenario.scenario_seed == config.get("scenario_seed", 0) and scenario.target_DoD == config.get("dynamicity", 0.5)
              and scenario.selection_mode == config.get("dynamic_selection_mode", "exact_count"), "scenario configuration mismatch")
        check(record["scenario"] == {**asdict(scenario), "scenario_hash": scenario.identifier}
              or identifier(record["scenario"]) == identifier({**asdict(scenario), "scenario_hash": scenario.identifier}),
              "embedded scenario mismatch")
        ref_config = ReferenceConfig(config.get("reference_solver_multistarts", 3),
                                     config.get("reference_improvement_passes", 1), config.get("reference_seed", 0),
                                     config.get("reference_label_limit", 24))
        key = identifier({"instance": instance.sha256, "config": asdict(ref_config),
                          "reference_solver_version": REFERENCE_SOLVER_VERSION})[:16]
        reference = ReferenceSchedule.load(ROOT / "data/reference_schedules" / f"{instance.name}_{key}.json", instance)
        check(scenario.reference_schedule_hash == reference.identifier, "stale reference hash")
        check(scenario.fleet_size == reference.fleet_size, "scenario/reference fleet mismatch")
        bounds = dict(scenario.release_upper_bounds)
        check(all(bounds[c.id] == min(c.ready, reference.predecessor_departures[c.id]) for c in instance.customers),
              "scenario release bounds mismatch")
        if ident["algorithm"] not in {"STATIC_REFERENCE", "ORACLE_REFERENCE"}:
            expected_config = simulation_config(config)
            if expected_config.algorithm == "MPC_MCTS_H1":
                expected_config = replace(expected_config, mpc=replace(expected_config.mpc, prediction_horizon=1))
            expected_data = asdict(expected_config)
            # V1 records predate opt-in fleet/root-coverage diagnostics.
            for field in ("fleet_mode", "diagnostics", "route_continuity", "route_insertion"):
                if field not in record["effective_config"] and field not in config:
                    expected_data.pop(field)
            for field in ("require_root_coverage", "max_idle_wait"):
                if field not in record["effective_config"]["mpc"] and field not in config:
                    expected_data["mpc"].pop(field)
            check(identifier(expected_data) == identifier(record["effective_config"]),
                  "unexpected effective configuration mismatch")
        check(record["algorithm"] == record["effective_config"], "algorithm section mismatch")
        required_fields = {
            "primary": {"complete_service", "customers_served", "customers_unserved", "service_ratio", "vehicles_activated", "total_distance"},
            "secondary": {"total_charging_visits", "total_energy_charged", "total_charging_time", "total_waiting_time", "final_return_feasibility"},
            "coordination": {"decision_epochs", "duplicate_customer_proposal_conflicts", "conflicts_resolved", "mean_unique_intention_coverage", "vehicle_activations_caused_by_coordinator", "wait_selected"},
            "computation": {"mean_planning_time", "median_planning_time", "p95_planning_time", "maximum_planning_time", "total_planning_time", "mcts_iterations", "nodes_expanded"},
            "integrity": {"battery_violations", "capacity_violations", "time_window_violations", "duplicate_service_violations", "hidden_information_violations", "trace_audit_passed"},
        }
        for section, fields in required_fields.items():
            check(fields.issubset(record[section]), f"missing fields in {section}")
        for section in ("primary", "secondary", "coordination", "computation", "integrity"):
            for name, value in record[section].items():
                if name == "trace_audit_passed":
                    check(value is True, "trace audit not passed")
                    continue
                check(isinstance(value, (int, float, bool)) and math.isfinite(value), f"missing/nonfinite outcome: {name}")
                check(value == record["metrics"].get(name), f"outcome section mismatch: {name}")
                if name.endswith("violations"):
                    check(value == 0, name)
        for name in ("customers_served", "customers_unserved", "service_ratio", "vehicles_activated", "total_distance"):
            check(name in record["primary"], f"missing primary outcome: {name}")
        check(record["primary"]["complete_service"] == (record["primary"]["customers_unserved"] == 0), "completion flag mismatch")
        audit_result(decode_result(record), instance, scenario)
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
    return errors


def audited_records(directory, keep_traces=True):
    records, rows = [], []
    for path in result_files(directory):
        try:
            record = load_json(path)
        except (ValueError, OSError) as error:
            record = {"status": "failed", "metadata": {}, "metrics": {}, "error": str(error)}
        if "status" not in record:
            continue
        errors = audit_record(record)
        run_id = record.get("identity", {}).get("run_id")
        incomplete = record.get("metrics", {}).get("customers_unserved", 0) > 0
        failure = "structural" if errors else "algorithm_failed" if record["status"] == "failed" else "incomplete_service" if incomplete else "none"
        rows.append(dict(path=str(path), run_id=run_id, structural_valid=not errors,
                         failure_class=failure, reason="; ".join(errors) or record.get("error", "")
                         or ("Not all customers served" if incomplete else "")))
        if not keep_traces:
            record = {k: v for k, v in record.items() if k not in {"steps", "events", "decisions", "searches"}}
        records.append(record)
    counts = Counter(row["run_id"] for row in rows if row["run_id"])
    for row in rows:
        if row["run_id"] and counts[row["run_id"]] > 1:
            row.update(structural_valid=False, failure_class="structural",
                       reason="; ".join(filter(None, [row["reason"], "duplicate run ID"])))
    return records, rows


def audit_directory(directory="results/raw", output="results/summaries"):
    _, rows = audited_records(directory, keep_traces=False)
    frame = pd.DataFrame(rows, columns=["path", "run_id", "structural_valid", "failure_class", "reason"])
    frame.to_csv(writable_path(Path(output) / "audit_report.csv"), index=False)
    invalid = sum(not r["structural_valid"] for r in rows)
    lines = ["# Result Audit", "", f"Records: {len(rows)}; structural failures: {invalid}.", "",
             "Incomplete service is a reported outcome, not a structural failure.", ""]
    lines.extend(f"- `{r['run_id'] or r['path']}`: {r['failure_class']}; {r['reason'] or 'passed'}" for r in rows)
    writable_path(Path(output) / "audit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return frame

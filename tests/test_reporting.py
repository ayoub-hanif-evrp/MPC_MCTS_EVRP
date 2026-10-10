from copy import deepcopy
from dataclasses import asdict
import json

import pandas as pd
import pytest

from evrp.analysis import aggregate, export_tables, hierarchical_summary, paired_differences, run_frame, wide_summary
from evrp.audit import audit_record, audited_records
from evrp.experiments import load_config, prepare, run_identity, run_single
from evrp.instance import load_instance
from evrp.plotting import make_figures
from evrp.reference import ReferenceFailure, ReferenceSchedule, solve_reference
from evrp.scenario import DynamicScenario, generate
from evrp.storage import BENCHMARK, save_json
from evrp.validation import validate_references


def test_run_identity_is_stable_and_configuration_sensitive():
    args = ("c101C5", "base", "scenario", {"study": "pilot", "top_L": 3}, "source", "commit")
    ident = run_identity(*args)
    assert ident == run_identity(*args)
    other = list(args)
    other[3] = {**args[3], "top_L": 5}
    assert ident["run_id"] != run_identity(*other)["run_id"]
    other = list(args)
    other[2] = "new scenario"
    assert ident["run_id"] != run_identity(*other)["run_id"]


def test_stale_reference_rejected(tmp_path):
    instance = load_instance(BENCHMARK / "c103C5.txt")
    reference = solve_reference(instance)
    path = tmp_path / "reference.json"
    reference.save(path)
    data = json.loads(path.read_text())
    data["reference_solver_version"] = "old"
    save_json(path, data)
    with pytest.raises(ReferenceFailure, match="Stale"):
        ReferenceSchedule.load(path, instance)


@pytest.mark.parametrize("field", ["schema_version", "base_instance_sha", "reference_schedule_hash",
                                    "reference_solver_version", "scenario_generator_version", "objective_version"])
def test_stale_scenario_dependencies_rejected(tmp_path, field):
    instance = load_instance(BENCHMARK / "c103C5.txt")
    scenario = generate(instance, solve_reference(instance), 0)
    data = asdict(scenario)
    data[field] = "obsolete"
    path = tmp_path / "scenario.json"
    save_json(path, data)
    with pytest.raises(ValueError, match="Stale|mismatch"):
        DynamicScenario.load(path, instance)


def test_prepare_reuses_scenario_without_redrawing(monkeypatch):
    config = load_config("configs/debug.yaml")
    first = prepare("c101C5", config)
    def forbidden(*args, **kwargs):
        raise AssertionError("Scenario was generated twice")
    monkeypatch.setattr("evrp.experiments.generate", forbidden)
    second = prepare("c101C5", {**config, "algorithm": "GREEDY"})
    assert first[2:] == second[2:]


def test_reference_validation_matches_published_small_cases(tmp_path):
    frame = validate_references(tmp_path)
    assert frame.validation_status.eq("passed").all()
    assert frame.vehicle_match.all()


@pytest.fixture(scope="module")
def valid_record(tmp_path_factory):
    config = {**load_config("configs/debug.yaml"), "mcts_iterations": 16}
    path = run_single("c101C5", config, tmp_path_factory.mktemp("record"))
    record = json.loads(path.read_text())
    assert record["status"] == "completed", record.get("error")
    return record


def test_schema_and_disk_trace_audit(valid_record):
    assert not audit_record(valid_record)
    assert valid_record["primary"]["customers_served"] > 0
    assert valid_record["identity"]["run_id"]
    altered = deepcopy(valid_record)
    altered["steps"][0]["distance"] += 1
    assert any("replay" in error for error in audit_record(altered))


@pytest.mark.parametrize("mutation", ["nan", "reference", "config", "missing", "metadata", "empty_section"])
def test_auditor_rejects_structural_corruption(valid_record, mutation):
    record = deepcopy(valid_record)
    if mutation == "nan":
        record["primary"]["total_distance"] = float("nan")
    elif mutation == "reference":
        record["scenario"]["reference_schedule_hash"] = "old"
    elif mutation == "config":
        record["effective_config"]["mpc"]["top_l"] = 999
    elif mutation == "metadata":
        record["metadata"]["scenario_identifier"] = "another-scenario"
    elif mutation == "empty_section":
        record["computation"] = {}
    else:
        del record["primary"]
    assert audit_record(record)


def test_duplicates_and_archives(valid_record, tmp_path):
    save_json(tmp_path / "a.json", valid_record)
    save_json(tmp_path / "b.json", valid_record)
    save_json(tmp_path / "archive_preobjective_fix" / "c.json", valid_record)
    runs, rows = audited_records(tmp_path)
    assert len(runs) == 2
    assert all("duplicate run ID" in row["reason"] for row in rows)


def test_compressed_trace_audit_and_streaming(valid_record, tmp_path):
    save_json(tmp_path / "run.json.gz", valid_record)
    records, audits = audited_records(tmp_path, keep_traces=False)
    assert audits[0]["structural_valid"]
    assert "steps" not in records[0] and records[0]["metrics"] == valid_record["metrics"]


def test_hierarchical_statistics_and_incomplete_distance():
    runs = []
    for instance, seed, service, distance in [("a", 0, 1, 100), ("a", 1, 1, 200), ("b", 0, .5, 2)]:
        runs.append(dict(status="completed", identity={"study": "pilot"}, metadata=dict(instance=instance,
                    scenario_identifier=instance, scenario_seed=0, algorithm_seed=seed, algorithm="GREEDY"),
                    metrics=dict(service_ratio=service, complete_service=service == 1, total_distance=distance)))
    frame = run_frame(runs)
    assert frame.distance_complete.isna().sum() == 1
    summary = hierarchical_summary(frame, ["algorithm"])
    service = summary[summary.metric == "service_ratio"].iloc[0]
    distance = summary[summary.metric == "distance_complete"].iloc[0]
    assert service["mean"] == .75 and service.n == 2
    assert distance["mean"] == 150 and distance.n == 1


def test_empty_ablation_headers_and_actual_max_latency():
    empty = wide_summary(hierarchical_summary(pd.DataFrame(), ["study", "algorithm"]))
    assert {"mean_service_ratio", "mean_activated_vehicles", "mean_distance_on_complete_runs", "mean_planning_time"} <= set(empty)
    frame = pd.DataFrame([dict(algorithm="GREEDY", instance="a", scenario_identifier="s", scenario_seed=0,
                               maximum_planning_time=value) for value in (1, 5)])
    summary = wide_summary(hierarchical_summary(frame, ["algorithm"]))
    assert summary.iloc[0].mean_run_max_planning_time == 3
    assert summary.iloc[0].maximum_planning_time == 5


def test_paired_conditions_and_seed_matching():
    rows = []
    for seed, a_service, b_service, a_vehicles, b_vehicles in [(0, 0, 0, 2, 2), (1, 0, 1, 2, 1), (2, 0, 0, 2, 3)]:
        for algorithm, service, vehicles, distance in [("COORDINATED_MPC_MCTS", a_service, a_vehicles, 100), ("GREEDY", b_service, b_vehicles, 80)]:
            rows.append(dict(instance="a", scenario_identifier="s", scenario_seed=0, algorithm_seed=seed,
                             source_sha256="code", algorithm=algorithm, status="completed",
                             customers_unserved=service, vehicles_activated=vehicles, total_distance=distance,
                             total_planning_time=1))
    frame = pd.DataFrame(rows)
    result = {r["metric"]: r for r in paired_differences(frame)}
    assert result["customers_unserved"]["eligible_pairs"] == 3
    assert result["vehicles_activated"]["eligible_pairs"] == 2
    assert result["total_distance"]["eligible_pairs"] == 1
    assert result["total_distance"]["mean"] == 20
    frame.loc[1, "scenario_identifier"] = "different"
    assert next(r for r in paired_differences(frame) if r["metric"] == "total_distance")["eligible_pairs"] == 0


def test_figure_csv_and_complete_only_distance(valid_record, tmp_path):
    save_json(tmp_path / "raw" / "run.json", valid_record)
    note = aggregate(tmp_path / "raw", tmp_path / "summary")
    assert note["structural_failures"] == 0
    tables = export_tables(tmp_path / "summary", tmp_path / "tables")
    assert len(tables) == 11  # Reference validation is a separate command.
    computation = pd.read_csv(tmp_path / "tables/csv/computation.csv")
    assert computation.maximum_planning_time.iloc[0] == pytest.approx(valid_record["metrics"]["maximum_planning_time"], abs=1e-6)
    paths = make_figures(tmp_path / "summary", tmp_path / "figures", study=valid_record["identity"]["study"])
    assert paths
    for path in paths:
        from pathlib import Path
        stem = Path(path)
        assert stem.exists() and stem.with_suffix(".png").exists()
        assert stem.suffix == ".png" and not stem.with_suffix(".pdf").exists()
        assert stem.with_name(stem.stem + "_data.csv").exists()
    distance = tmp_path / "figures/main/distance_vs_dod_data.csv"
    if valid_record["primary"]["complete_service"]:
        assert set(pd.read_csv(distance).metric) == {"distance_complete"}
    else:
        assert not distance.exists()
    with pytest.raises(ValueError, match="No audited observations"):
        make_figures(tmp_path / "summary", tmp_path / "figures", study="not_run")


def test_analysis_retains_route_ablation_settings():
    run = dict(status="completed", effective_config=dict(route_continuity=False,
               regret_repair=True, fleet_mode="fixed_reference", mpc=dict(proposal_selection="coverage_diverse")))
    row = run_frame([run]).iloc[0]
    assert not row.route_continuity and row.regret_repair
    assert row.proposal_selection == "coverage_diverse"

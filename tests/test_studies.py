"""Study orchestration tests use synthetic records only, never real solvers."""

from copy import deepcopy
from itertools import product
from pathlib import Path
from types import SimpleNamespace

import pytest

from evrp import cli, studies
from evrp.experiments import load_config
from evrp.storage import identifier, load_json, save_json

REPO = Path(__file__).resolve().parents[1]


def record(name="c101_21", dod=0.5, algorithm="COORDINATED_MPC_MCTS", unserved=0,
           vehicles=3, distance=100, seed=0):
    return dict(status="completed", metadata=dict(instance=name, DoD_target=dod, DoD_realized=dod,
                scenario_seed=seed, algorithm_seed=0, algorithm=algorithm,
                scenario_identifier=identifier((name, dod, seed))),
                metrics=dict(customers_unserved=unserved, customers_served=100-unserved,
                             service_ratio=(100-unserved)/100, vehicles_activated=vehicles,
                             total_distance=distance, p95_planning_time=0.1, final_return_feasibility=True))


def stage1_records():
    return [record(name, dod, algorithm) for name, dod, algorithm in
            product(studies.SCREEN_INSTANCES, (0.0, 0.5), studies.ALGORITHMS)]


@pytest.fixture
def synthetic(tmp_path, monkeypatch):
    monkeypatch.setattr(studies, "ROOT", tmp_path)
    benchmark = tmp_path / "benchmark"
    benchmark.mkdir()
    for name in studies.SCREEN_INSTANCES:
        (benchmark / f"{name}.txt").write_text(name, encoding="ascii")
    monkeypatch.setattr(studies, "BENCHMARK", benchmark)
    monkeypatch.setattr(studies, "source_fingerprint", lambda: "synthetic-source")
    from evrp import audit
    monkeypatch.setattr(audit, "audit_record", lambda raw: [])
    state = SimpleNamespace(prepared=[], executed=[], fail_static=False, ineligible_dod=None,
                            fail_run=False, dynamic_incomplete=0)

    def prepare(name, config):
        state.prepared.append((name, config.copy()))
        dod, seed = config["dynamicity"], config["scenario_seed"]
        realized = 0 if dod == state.ineligible_dod else dod
        data = dict(target_DoD=dod, realized_DoD=realized, scenario_seed=seed,
                    fleet_size=4, instance_sha256=studies._file_hash(benchmark / f"{name}.txt"),
                    reference_schedule_identifier=f"ref-{name}")
        path = studies.result_path(f"results/cache/scenarios/{name}_{dod}_{seed}.json")
        save_json(path, data)
        scenario = SimpleNamespace(**data, identifier=identifier(data))
        instance = SimpleNamespace(name=name, sha256=data["instance_sha256"], customers=range(100))
        reference = SimpleNamespace(identifier=f"ref-{name}", fleet_size=4)
        return instance, reference, scenario, path

    def run_single(name, config, output):
        state.executed.append((name, config.copy()))
        data = load_json(config["scenario_path"])
        coordinated = config["algorithm"] == studies.ALGORITHMS[2]
        unserved = int(state.fail_static and coordinated and config["dynamicity"] == 0)
        if coordinated and config["dynamicity"] == 0.5 and name in studies.SCREEN_INSTANCES[:state.dynamic_incomplete]:
            unserved = 1
        raw = record(name, config["dynamicity"], config["algorithm"], unserved,
                     vehicles=3 if coordinated else 4, seed=config["scenario_seed"])
        raw["metadata"]["scenario_identifier"] = identifier(data)
        raw["metadata"]["DoD_realized"] = data["realized_DoD"]
        raw.update(requested_config=config, provenance={"source_sha256": "synthetic-source"},
                   identity={"scenario_hash": identifier(data)})
        if state.fail_run:
            raw["status"] = "failed"
        path = output / f"{identifier((name, config))}.json"
        save_json(path, raw)
        return path

    monkeypatch.setattr(studies, "prepare", prepare)
    monkeypatch.setattr(studies, "run_single", run_single)
    return state


def screen_config():
    return {"gate": {"bootstrap_samples": 100}}


def test_exact_configs_and_defaults():
    assert {p.stem for p in (REPO / "configs").glob("*.yaml")} == {
        "debug", "validation", "smoke", "screening", "main", "ablations", "realtime"}
    for path in (REPO / "configs").glob("*.yaml"):
        config = load_config(path)
        assert config["fleet_mode"] == "fixed_reference"
        assert config["route_continuity"] is True
        assert config["regret_repair"] is True
        assert config["proposal_selection"] == "quality"
        assert config["max_idle_wait"] == 0


def test_prescribed_plans_have_36_and_108_runs():
    config = load_config(REPO / "configs/screening.yaml")
    for stage, count in (("stage1", 36), ("stage2", 108)):
        plan = studies.plan_study(stage, config)
        assert len(plan) == count
        assert {name for name, _ in plan} == set(studies.SCREEN_INSTANCES)
        for _, effective in plan:
            assert (effective["mcts_iterations"], effective["prediction_horizon"], effective["top_L"]) == (32, 5, 3)
            assert effective["experiment_seed"] == 0
    assert {c["scenario_seed"] for _, c in studies.plan_study("stage2", config)} == {0, 1}


@pytest.mark.parametrize("changes", [{"mcts_iterations": 64}, {"fleet_mode": "lazy_reserve"},
                                    {"route_continuity": False}, {"regret_repair": False},
                                    {"max_idle_wait": 10}, {"grid": {}}, {"scenario_path": "other.json"},
                                    {"instances": ["c101_21"]}])
def test_screening_cannot_change_prescribed_conditions(changes):
    with pytest.raises(ValueError):
        studies.plan_study("stage1", changes)


def test_stage1_reports_all_methods_but_gates_coordinated():
    records = stage1_records()
    for raw in records:
        if raw["metadata"]["algorithm"] == "RH_REGRET":
            raw["metrics"].update(customers_unserved=30, service_ratio=0.7)
    decision = studies.stage1_gate(records)
    assert decision["status"] == "PASS"
    assert decision["algorithms"]["RH_REGRET"]["static_complete"] == 0
    assert studies.stage1_gate(records[:-1])["status"] == "FAIL"


@pytest.mark.parametrize("unserved,expected", [([0, 0, 0, 0, 0, 12], "PASS"),
                                                          ([0, 0, 0, 0, 0, 13], "FAIL"),
                                                          ([0, 0, 0, 0, 1, 1], "FAIL")])
def test_stage1_mean_and_five_complete_are_both_required(unserved, expected):
    records = stage1_records()
    dynamic = [r for r in records if r["metadata"]["algorithm"] == studies.ALGORITHMS[2] and r["metadata"]["DoD_target"] == 0.5]
    for raw, count in zip(dynamic, unserved):
        raw["metrics"].update(customers_unserved=count, service_ratio=(100-count)/100)
    assert studies.stage1_gate(records)["status"] == expected


def test_paired_conditional_metrics_and_deterministic_bootstrap():
    records = []
    for name, coord, other in (("c101_21", (0, 5, 150), (1, 2, 80)),
                                ("r101_21", (0, 3, 140), (0, 4, 90)),
                                ("rc101_21", (0, 3, 80), (0, 3, 100))):
        records.append(record(name, unserved=coord[0], vehicles=coord[1], distance=coord[2]))
        records.extend(record(name, algorithm=a, unserved=other[0], vehicles=other[1], distance=other[2]) for a in studies.ALGORITHMS[:2])
    gate = studies.screening_gate(records)
    assert gate["status"] == "PASS"
    stats = gate["comparisons"]["RH_REGRET"]["metrics"]
    assert stats["customers_unserved"]["n"] == 3
    assert stats["vehicles_activated"]["n"] == 2
    assert stats["vehicles_activated"]["mean"] == -0.5
    assert stats["total_distance"]["n"] == 1
    assert stats["total_distance"]["mean"] == -20
    assert stats["total_distance"]["ci95"] == [None, None]
    values = [-4, -1, 0, 2]
    assert studies.paired_statistics(values) == studies.paired_statistics(reversed(values))
    assert studies.paired_statistics(values)["wins"] == 2
    assert studies.paired_statistics([])["mean"] is None


def test_stage1_failure_stops_before_stage2(synthetic):
    synthetic.fail_static = True
    gate = studies.run_screening(screen_config())
    assert gate["status"] == "FAIL"
    assert len(synthetic.executed) == 36
    assert len(synthetic.prepared) == 12
    assert "stage2" not in gate


def test_full_screening_shared_scenarios_and_eligibility(synthetic):
    synthetic.ineligible_dod = 0.75
    config = screen_config()
    gate = studies.run_screening(config)
    assert gate["status"] == "PASS"
    assert len(synthetic.executed) == 36 + 72
    assert len(synthetic.prepared) == 12 + 36
    assert len(gate["ineligible"]) == 12
    manifest = load_json(studies.result_path("results/screening/stage2/manifest.json"))
    assert manifest["planned_runs"] == 108
    assert len(manifest["runs"]) == 72
    assert studies.require_screening_pass(config)["status"] == "PASS"
    for entry in manifest["scenarios"]:
        matching = [r for r in manifest["runs"] if r["requested_config"]["scenario_path"] == entry["scenario_path"]]
        assert len(matching) == (3 if entry["eligible"] else 0)
    assert "95% CI" in studies.result_path("results/screening/GATE.md").read_text()


@pytest.mark.parametrize("change", ["source", "config", "benchmark", "result", "scenario", "manifest", "gate"])
def test_gate_rejects_stale_or_changed_evidence(synthetic, monkeypatch, change):
    config = screen_config()
    studies.run_screening(config)
    manifest_path = studies.result_path("results/screening/stage2/manifest.json")
    manifest = load_json(manifest_path)
    if change == "source":
        monkeypatch.setattr(studies, "source_fingerprint", lambda: "new-source")
    elif change == "config":
        config["candidate_limit"] = 13
    elif change == "benchmark":
        (studies.BENCHMARK / "c101_21.txt").write_text("changed", encoding="ascii")
    elif change == "result":
        path = manifest["runs"][0]["path"]
        raw = load_json(path)
        raw["metrics"]["total_distance"] += 1
        save_json(path, raw)
    elif change == "scenario":
        path = manifest["scenarios"][0]["scenario_path"]
        raw = load_json(path)
        raw["realized_DoD"] = 0.99
        save_json(path, raw)
    elif change == "manifest":
        manifest["runs"].pop()
        save_json(manifest_path, manifest)
    else:
        path = studies.result_path("results/screening/GATE.json")
        gate = load_json(path)
        gate["stage2"]["comparisons"]["RH_REGRET"]["improving_pairs"] = 999
        save_json(path, gate)
    with pytest.raises(ValueError):
        studies.require_screening_pass(config)


def test_stage2_requires_fresh_stage1_before_any_runs(synthetic, monkeypatch):
    config = screen_config()
    gate = studies.run_screening(config, stage="1")
    assert gate["status"] == "BLOCKED" and gate["stage1"]["status"] == "PASS"
    count = len(synthetic.executed)
    monkeypatch.setattr(studies, "source_fingerprint", lambda: "new-source")
    with pytest.raises(ValueError, match="stale"):
        studies.run_screening(config, stage="2")
    assert len(synthetic.executed) == count


def test_failed_record_blocks_gate(synthetic):
    synthetic.fail_run = True
    with pytest.raises(RuntimeError, match="RH_REGRET"):
        studies.run_screening(screen_config())
    assert load_json(studies.result_path("results/screening/GATE.json"))["status"] == "FAIL"
    assert len(synthetic.executed) == 1


@pytest.mark.parametrize("study,count", [("main", 324), ("ablations", 108), ("realtime", 24)])
def test_later_studies_require_execute_and_gate(synthetic, study, count):
    config = load_config(REPO / f"configs/{study}.yaml")
    plan = studies.run_study(study, config, f"results/{study}")
    assert plan["status"] == "PLANNED" and plan["planned_runs"] == count
    assert not synthetic.prepared and not synthetic.executed
    with pytest.raises((ValueError, OSError)):
        studies.run_study(study, config, f"results/{study}", execute=True, screening_config=screen_config())
    assert not synthetic.prepared and not synthetic.executed


def test_changed_scientific_config_cannot_reuse_pass(synthetic):
    studies.run_screening(screen_config())
    config = {"instances": ["c101_21"], "prediction_horizon": 3}
    count = len(synthetic.executed)
    with pytest.raises(ValueError, match="scientific configuration"):
        studies.run_study("main", config, "results/main", execute=True, screening_config=screen_config())
    assert len(synthetic.executed) == count


def test_main_runs_only_after_explicit_execute_with_pass(synthetic):
    studies.run_screening(screen_config())
    count = len(synthetic.executed)
    config = {"instances": ["c101_21"], "grid": {"algorithm": list(studies.ALGORITHMS)}}
    result = studies.run_study("main", config, "results/main", execute=True, screening_config=screen_config())
    assert result["status"] == "completed"
    assert len(synthetic.executed) == count + 3


def test_realtime_is_sequential_and_ablation_is_one_factor():
    realtime = load_config(REPO / "configs/realtime.yaml")
    assert len(studies.plan_study("realtime", realtime)) == 24
    with pytest.raises(ValueError, match="isolation"):
        studies.plan_study("realtime", {**realtime, "outer_workers": 2})
    ablations = load_config(REPO / "configs/ablations.yaml")
    baseline = studies.runtime_config(ablations)
    for _, variant in studies.plan_study("ablations", ablations):
        differences = {key for key in baseline if variant[key] != baseline[key]}
        assert differences <= {"scenario_seed", "algorithm", "route_continuity", "regret_repair", "prediction_horizon", "top_L", "proposal_selection"}
        assert len(differences - {"scenario_seed"}) <= 1


@pytest.mark.parametrize("path", ["../outside", "results/../../outside", "configs", "results/../configs"])
def test_outputs_confined(synthetic, path):
    with pytest.raises(ValueError, match="results/"):
        studies.result_path(path)


def test_cli_main_defaults_to_planning_and_rejects_outside_output(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("Planning must never call execution")
    monkeypatch.setattr(studies, "prepare", forbidden)
    monkeypatch.setattr(studies, "run_single", forbidden)
    cli.main(["main"])
    assert '"status": "PLANNED"' in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        cli.main(["run", "--instance", "c101C5", "--output", "../outside"])
    assert error.value.code == 1

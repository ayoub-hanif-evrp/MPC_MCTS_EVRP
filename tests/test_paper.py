from itertools import product

import pytest

from evrp.paper import CALIBRATION, paper_plan, canonical_config, experiment_key, select_budget, validate_launch


def test_compact_design_counts_and_cross_study_reuse():
    jobs, members = paper_plan({"mcts_iterations": 32})
    assert {s: sum(m["study"] == s for m in members) for s in "ABCDE"} == {
        "A": 224, "B": 384, "C": 90, "D": 84, "E": 24}
    assert len(jobs) == 704
    keys = lambda study: {m["key"] for m in members if m["study"] == study}
    assert len(keys("D")) == 60
    assert len(keys("A") & keys("B")) == 48
    assert len(keys("C") & keys("A")) == 18
    assert sum(j["isolated"] for j in jobs) == 24
    assert all(j["config"]["mcts_iterations"] <= 64 for j in jobs)
    assert all(not j["config"]["parallel_agents"] for j in jobs if not j["isolated"])


def test_calibration_matches_paper_cells():
    jobs, _ = paper_plan({"mcts_iterations": 32})
    keys = {j["key"] for j in jobs}
    assert all(experiment_key(i, canonical_config(dict(mcts_iterations=b))) in keys
               for i, b in product(CALIBRATION, (8, 16, 32, 64)))


def calibration_rows():
    return [dict(instance=i, iterations=b, customers_served=50+(b >= 16),
                 vehicles_activated=10, total_distance=100, status="completed", audit_errors=[])
            for i, b in product(CALIBRATION, (8, 16, 32, 64))]


def test_predefined_budget_rule_and_incomplete_fallback():
    rows = calibration_rows()
    assert select_budget(rows)["budget"] == 16  # Eight has no equal-service pairs.
    assert select_budget(rows[:-1])["budget"] == 32
    assert not select_budget(rows[:-1])["clear"]
    for row in rows:
        if row["iterations"] == 16:
            row["total_distance"] = 106
    assert select_budget(rows)["budget"] == 32


def test_launch_is_explicit_and_calibration_bound():
    with pytest.raises(RuntimeError, match="Planning only"):
        validate_launch({}, {}, {}, execute=False)
    with pytest.raises(RuntimeError, match="stale"):
        validate_launch({}, {}, {}, execute=True)


def test_legacy_launches_are_disabled():
    from evrp.campaign import execute
    from scripts.run_full_campaign import execute as parallel_execute
    with pytest.raises(RuntimeError, match="cancelled"):
        execute()
    with pytest.raises(RuntimeError, match="cancelled"):
        parallel_execute()


def test_launch_rejects_changed_calibrated_method(monkeypatch):
    import evrp.paper as paper
    import evrp.audit as audit
    rows = calibration_rows()
    for row in rows:
        row.update(path="fixture.json.gz", wall_seconds=1)
    report = dict(source_sha256="fixture", rows=rows, selection=select_budget(rows))
    monkeypatch.setattr(paper, "source_fingerprint", lambda: "fixture")
    monkeypatch.setattr(paper, "load_json", lambda path: {
        "provenance": {"source_sha256": "fixture"}, "requested_config": canonical_config()})
    monkeypatch.setattr(audit, "audit_record", lambda raw: [])
    estimate = dict(estimated_parallel_seconds=60, resource={"workers": 1})
    paper.validate_launch({"mcts_iterations": 16}, report, estimate, execute=True)
    with pytest.raises(RuntimeError, match="differs from the calibrated"):
        paper.validate_launch({"mcts_iterations": 16, "station_candidate_limit": 8}, report, estimate, execute=True)
    with pytest.raises(RuntimeError, match="few-hour"):
        paper.validate_launch({"mcts_iterations": 16}, report,
                              {**estimate, "estimated_parallel_seconds": 7*3600}, execute=True)


def test_timing_panels_keep_profiles_separate():
    import pandas as pd
    import matplotlib.pyplot as plt
    from evrp.plotting import _panel
    frame = pd.DataFrame([dict(algorithm="GREEDY", execution_profile=p, x=1, metric="mean_planning_time",
                               n=1, mean=value, ci95_low=None, ci95_high=None)
                          for p, value in (("isolated", 1), ("concurrent", 3))])
    fig, ax = plt.subplots()
    _panel(ax, frame, "x", "mean_planning_time", "Timing")
    assert len(ax.lines) == 2
    assert {line.get_label() for line in ax.lines} == {"Greedy (isolated)", "Greedy (concurrent)"}
    plt.close(fig)

import json

import pytest

from evrp import campaign
from evrp.storage import load_json, save_json


def test_full_campaign_counts_and_lossless_storage():
    _, jobs = campaign.plan()
    assert sum(j[0] == "main" for j in jobs) == 224
    assert len(jobs) < 1000
    assert all(config["result_compression"] == "gzip" for _, _, config in jobs)


def test_gzip_roundtrip(tmp_path):
    path = tmp_path / "run.json.gz"
    data = {"steps": [{"distance": 1.234567890123, "customer": "C1"}] * 100}
    save_json(path, data)
    assert load_json(path) == data
    assert path.stat().st_size < len(json.dumps(data))


def test_campaign_lifecycle_and_revision_guard(tmp_path, monkeypatch):
    config = {"algorithm": "GREEDY", "study": "pilot"}
    monkeypatch.setattr(campaign, "plan", lambda studies: ({"pilot": config}, [("pilot", "c101C5", config)]))
    monkeypatch.setattr(campaign, "source_fingerprint", lambda: "revision-one")
    monkeypatch.setattr(campaign, "require_reference_validation", lambda: None)
    calls = []
    def run(instance, effective, output):
        path = output / "test.json.gz"
        save_json(path, {"status": "completed", "metrics": {"customers_served": 5}})
        return path
    monkeypatch.setattr(campaign, "run_single", run)
    monkeypatch.setattr(campaign, "render_reports", lambda directory, completed: calls.append(list(completed)) or {"structural_failures": 0})
    campaign.execute(tmp_path, ("pilot",))
    state = load_json(tmp_path / "status.json")
    assert state["status"] == "completed" and state["completed"] == state["total"] == 1
    assert calls == [["pilot"]]
    campaign.execute(tmp_path, ("pilot",))
    monkeypatch.setattr(campaign, "source_fingerprint", lambda: "revision-two")
    with pytest.raises(RuntimeError, match="changed"):
        campaign.execute(tmp_path, ("pilot",))


def test_campaign_lock_prevents_two_runners(tmp_path):
    with campaign.exclusive_runner(tmp_path / "runner.lock"):
        with pytest.raises(OSError):
            with campaign.exclusive_runner(tmp_path / "runner.lock"):
                pytest.fail("Second runner acquired the lock")

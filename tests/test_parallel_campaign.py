from scripts.run_full_campaign import capacity, is_isolated, available_memory_mib
from scripts.run_full_campaign import worker
from concurrent.futures import ProcessPoolExecutor
from evrp.audit import audit_record
from evrp.storage import load_json


def test_timing_studies_have_isolation_barriers():
    assert is_isolated("pilot", {})
    assert is_isolated("realtime", {})
    assert is_isolated("ablations", {"ablation_factor": "parallel_agents"})
    assert not is_isolated("main", {})
    assert not is_isolated("ablations", {"ablation_factor": "prediction_horizon"})


def test_memory_aware_capacity():
    assert capacity(0, 4, 1024) == 2
    assert capacity(2, 4, 200) == 2
    assert capacity(1, 4, 2000) == 4
    assert capacity(0, 1, 2000) == 1
    assert capacity(0, 4, 200) == 0
    assert capacity(0, 4, 300, resident=2) == 2
    assert available_memory_mib() > 0


def test_two_processes_share_dependencies_safely(tmp_path):
    config = {"study": "pilot", "algorithm": "GREEDY", "result_compression": "gzip"}
    with ProcessPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker, str(tmp_path), "c101C5", {**config, "experiment_seed": seed}) for seed in (0, 1)]
        results = [future.result(timeout=90) for future in futures]
    assert all(result["status"] == "completed" for result in results)
    assert len({result["run_id"] for result in results}) == 2
    assert all(not audit_record(load_json(result["path"])) for result in results)

"""Memory-aware multicore campaign; realtime and parallelism comparisons isolated."""

import os
for _variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_variable] = "1"

import argparse
from collections import deque
from contextlib import ExitStack
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import Event, Lock, Thread
from time import perf_counter, sleep
import ctypes
import json
import shutil
import traceback

from evrp.campaign import STUDIES, exclusive_runner, plan, render_reports
from evrp.experiments import prepare, run_single, source_fingerprint
from evrp.storage import ROOT, identifier, load_json, save_json
from evrp.validation import require_reference_validation


def available_memory_mib():
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        *[(name, ctypes.c_ulonglong) for name in
                          ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("Cannot determine available physical memory")
        return status.available / 1024**2
    return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**2


def is_isolated(study, config):
    return study in {"pilot", "realtime"} or config.get("ablation_factor") == "parallel_agents"


def capacity(running, maximum, free_mib, resident=0):
    # Reserve room for the OS and avoid spawning several scientific Python stacks at once.
    idle = max(0, resident - running) if free_mib >= 256 else 0
    additions = idle + max(0, int((free_mib - 256) // 320))
    return min(maximum, running + additions)


def worker(directory, instance, config):
    started = perf_counter()
    # Different agents/algorithms can share a scenario. Serialize only artifact creation.
    with ExitStack() as locks:
        while True:
            try:
                locks.enter_context(exclusive_runner(Path(directory) / "dependency_locks" / f"{instance}.lock"))
                break
            except OSError as error:
                if isinstance(error, PermissionError) or getattr(error, "winerror", None) in {33, 36}:
                    sleep(.25)
                else:
                    raise
        try:
            prepare(instance, config)
        except Exception:
            # run_single below writes the dependency failure as a normal failed-run record.
            pass
    path = run_single(instance, config, Path(directory) / "raw" / config["study"])
    record = load_json(path)
    return dict(path=str(path), status=record["status"], run_id=record["identity"]["run_id"],
                seconds=perf_counter() - started, metrics=record["metrics"], error=record.get("error"),
                process_id=os.getpid())


def execute(directory="results/campaigns/final", workers=4):
    raise RuntimeError("The old campaign is cancelled. Use python -m evrp.cli estimate --config configs/paper.yaml")


def _archived_execute(directory="results/campaigns/final", workers=4):
    if workers < 1:
        raise ValueError("Worker count must be positive")
    directory = Path(directory).resolve()
    configs, jobs = plan()
    source = source_fingerprint()
    executor_hash = sha256(Path(__file__).read_bytes()).hexdigest()
    executor_signature = identifier(dict(source=source, executor=executor_hash, configs=configs, workers=workers))
    manifest_path = directory / "parallel_manifest.json"
    if manifest_path.exists() and load_json(manifest_path)["signature"] != executor_signature:
        raise RuntimeError("Parallel campaign source/configuration changed; choose a new output directory")
    with exclusive_runner(directory / "runner.lock"):
        save_json(manifest_path, dict(signature=executor_signature, source_sha256=source,
                  executor_sha256=executor_hash, configs=configs, max_workers=workers, total_runs=len(jobs),
                  timing_policy="Concurrent fixed-iteration studies; realtime and parallel-agent comparisons have one active experiment"))
        state = dict(status="validating", pid=os.getpid(), total=len(jobs), completed=0, failed=0,
                     max_workers=workers, running=[], completed_studies=[], study_counts={},
                     started_at=datetime.now(timezone.utc).isoformat())
        lock, stop = Lock(), Event()
        start = perf_counter()

        def persist():
            with lock:
                state.update(heartbeat=datetime.now(timezone.utc).isoformat(),
                             elapsed_seconds=perf_counter()-start, available_memory_mib=available_memory_mib())
                save_json(directory / "status.json", state)

        def heartbeat():
            while not stop.wait(10):
                persist()

        persist()
        monitor = Thread(target=heartbeat, daemon=True)
        monitor.start()
        executor = ProcessPoolExecutor(max_workers=workers)
        resident = 0
        try:
            require_reference_validation()
            for study in STUDIES:
                pending = deque((index + 1, instance, config) for index, (s, instance, config) in enumerate(jobs) if s == study)
                active = {}
                while pending or active:
                    if source_fingerprint() != source or sha256(Path(__file__).read_bytes()).hexdigest() != executor_hash:
                        raise RuntimeError("Source changed; refusing mixed revisions")
                    if shutil.disk_usage(directory).free < 10 * 1024**3:
                        raise RuntimeError("Less than 10 GiB free; stopping before disk exhaustion")
                    isolated_active = any(info["isolated"] for info in active.values())
                    while pending and not isolated_active:
                        index, instance, original = pending[0]
                        isolated = is_isolated(study, original)
                        if isolated and active:
                            break
                        if len(active) >= capacity(len(active), 1 if isolated else workers, available_memory_mib(), resident):
                            break
                        pending.popleft()
                        config = dict(original)
                        # Pilot records keep their exact original identity and are resumed, not duplicated.
                        if study != "pilot":
                            config.update(execution_profile="isolated_campaign" if isolated else "concurrent_campaign",
                                          campaign_workers=1 if isolated else workers,
                                          campaign_executor_sha256=executor_hash, numerical_thread_limit=1)
                        info = dict(index=index, study=study, instance=instance, algorithm=config["algorithm"],
                                    config=config, isolated=isolated, started_at=datetime.now(timezone.utc).isoformat())
                        future = executor.submit(worker, directory, instance, config)
                        active[future] = info
                        resident = max(resident, len(active))
                        isolated_active = isolated
                        # Allow the newly spawned worker's memory footprint to become visible.
                        sleep(.5)
                    with lock:
                        state.update(status="running" if active else "waiting_for_memory", current_study=study,
                                     running=list(active.values()), pending_in_study=len(pending))
                    persist()
                    if not active:
                        sleep(5)
                        continue
                    done, _ = wait(active, timeout=5, return_when=FIRST_COMPLETED)
                    for future in done:
                        info = active.pop(future)
                        result = future.result()
                        event = dict(**info, **result, finished_at=datetime.now(timezone.utc).isoformat())
                        with (directory / "execution.jsonl").open("a", encoding="utf-8") as stream:
                            stream.write(json.dumps(event, allow_nan=False) + "\n")
                        with lock:
                            state["completed"] += 1
                            state["failed"] += int(result["status"] == "failed")
                            state["study_counts"][study] = state["study_counts"].get(study, 0) + 1
                            state["last_result"] = result
                            state["running"] = list(active.values())
                        persist()
                        print(json.dumps(dict(index=info["index"], completed=state["completed"], total=len(jobs),
                              study=study, instance=info["instance"], algorithm=info["algorithm"],
                              seconds=result["seconds"], status=result["status"], error=result["error"])), flush=True)
                with lock:
                    state["completed_studies"].append(study)
                    state["status"] = "generating_reports"
                persist()
                note = render_reports(directory, state["completed_studies"])
                import pandas as pd
                events = pd.read_json(directory / "execution.jsonl", lines=True)
                context = events[["run_id", "study", "instance", "algorithm", "isolated", "seconds", "process_id", "started_at", "finished_at"]]
                context.drop_duplicates("run_id", keep="last").to_csv(directory / "summaries/timing_context.csv", index=False)
                with lock:
                    state["audit"] = note
            with lock:
                state.update(status="completed_with_failures" if state["failed"] or note["structural_failures"] else "completed",
                             finished_at=datetime.now(timezone.utc).isoformat())
            persist()
        except BaseException as error:
            with lock:
                state.update(status="error", error=str(error), traceback=traceback.format_exc())
            persist()
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
            stop.set()
            monitor.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/campaigns/final")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    execute(args.output, args.workers)


if __name__ == "__main__":
    main()

"""Resumable sequential execution of every configured research study."""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from time import perf_counter
import argparse
import json
import os
import shutil
import traceback

from .experiments import grid_cases, load_config, run_single, source_fingerprint
from .storage import ROOT, identifier, save_json, writable_path, load_json
from .validation import require_reference_validation, validate_references

STUDIES = ("pilot", "ablations", "realtime", "main")


def plan(studies=STUDIES):
    configs = {study: load_config(ROOT / "configs" / f"{study}.yaml") for study in studies}
    jobs = [(study, instance, {**effective, "result_compression": "gzip"}) for study, config in configs.items()
            for instance, effective in grid_cases(config, study == "ablations")]
    return configs, jobs


@contextmanager
def exclusive_runner(path):
    handle = writable_path(path).open("a+b")
    try:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        handle.close()


def render_reports(directory, completed_studies):
    from .analysis import aggregate, export_tables
    from .plotting import make_figures, make_realtime_figures, representative_figures
    summaries = directory / "summaries"
    note = aggregate(directory / "raw", summaries)
    validate_references(summaries)
    export_tables(summaries, directory / "tables")
    if "pilot" in completed_studies:
        make_figures(summaries, directory / "figures/pilot", "pilot")
        representative_figures(directory / "raw/pilot", directory / "figures/representative")
    if "realtime" in completed_studies:
        make_realtime_figures(summaries, directory / "figures/realtime")
    if "main" in completed_studies:
        make_figures(summaries, directory / "figures", "main")
    return note


def execute(directory="results/campaigns/final", studies=STUDIES):
    directory = Path(directory).resolve()
    configs, jobs = plan(studies)
    source = source_fingerprint()
    signature = identifier({"source": source, "configs": configs})
    manifest = directory / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text())["signature"] != signature:
        raise RuntimeError("Campaign source/configuration changed; use a new output directory to avoid mixed results")
    with exclusive_runner(directory / "runner.lock"):
        save_json(manifest, dict(signature=signature, source_sha256=source, configs=configs,
                                 total_runs=len(jobs), study_counts={s: sum(j[0] == s for j in jobs) for s in studies}))
        state = dict(status="validating", pid=os.getpid(), total=len(jobs), completed=0, failed=0,
                     completed_studies=[], current=None, study_counts={}, started_at=datetime.now(timezone.utc).isoformat())
        started, lock, stop = perf_counter(), Lock(), Event()

        def persist():
            with lock:
                state["heartbeat"] = datetime.now(timezone.utc).isoformat()
                state["elapsed_seconds"] = perf_counter() - started
                save_json(directory / "status.json", state)

        def heartbeat():
            while not stop.wait(10):
                persist()

        persist()
        thread = Thread(target=heartbeat, daemon=True)
        thread.start()
        previous = None
        try:
            require_reference_validation()
            for index, (study, instance, config) in enumerate(jobs):
                if source_fingerprint() != source:
                    raise RuntimeError("Source changed while campaign was running; refusing mixed revisions")
                if shutil.disk_usage(directory).free < 10 * 1024**3:
                    raise RuntimeError("Less than 10 GiB free; campaign stopped safely before filling the disk")
                if previous is not None and study != previous:
                    with lock:
                        state["completed_studies"].append(previous)
                        state["status"] = "generating_reports"
                    persist()
                    render_reports(directory, state["completed_studies"])
                previous = study
                with lock:
                    state.update(status="running", current=dict(index=index + 1, study=study, instance=instance,
                                 algorithm=config["algorithm"], config=config), current_started_at=datetime.now(timezone.utc).isoformat())
                persist()
                before = perf_counter()
                path = run_single(instance, config, directory / "raw" / study)
                record = load_json(path)
                elapsed = perf_counter() - before
                with lock:
                    state["completed"] += 1
                    state["failed"] += int(record["status"] == "failed")
                    state["study_counts"][study] = state["study_counts"].get(study, 0) + 1
                    state["last_result"] = dict(path=str(path), status=record["status"], elapsed_seconds=elapsed,
                                                 metrics=record["metrics"], error=record.get("error"))
                persist()
                print(json.dumps(dict(index=index + 1, total=len(jobs), study=study, instance=instance,
                      algorithm=config["algorithm"], status=record["status"], seconds=elapsed,
                      served=record["metrics"].get("customers_served"), error=record.get("error"))), flush=True)
            with lock:
                state["completed_studies"].append(previous)
                state["status"] = "generating_reports"
                state["current"] = None
            persist()
            note = render_reports(directory, state["completed_studies"])
            with lock:
                state.update(status="completed_with_failures" if state["failed"] or note["structural_failures"] else "completed",
                             audit=note, finished_at=datetime.now(timezone.utc).isoformat())
            persist()
        except BaseException as error:
            with lock:
                state.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "error",
                             error=str(error), traceback=traceback.format_exc())
            persist()
            raise
        finally:
            stop.set()
            thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="results/campaigns/final")
    parser.add_argument("--studies", nargs="+", choices=STUDIES, default=list(STUDIES))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        _, jobs = plan(args.studies)
        print(json.dumps({"total": len(jobs), "studies": {s: sum(j[0] == s for j in jobs) for s in args.studies}}, indent=2))
    else:
        execute(args.output, args.studies)


if __name__ == "__main__":
    main()

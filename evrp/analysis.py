"""Descriptive research statistics, retaining failed and infeasible runs."""

from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy.stats import t

from .storage import save_json, writable_path


def load_runs(directory: str | Path) -> list[dict]:
    results = []
    for path in sorted(Path(directory).glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if "status" in record and "metadata" in record:
            results.append(record)
    return results


def run_frame(runs: list[dict]) -> pd.DataFrame:
    rows = []
    for run in runs:
        row = {**run["metadata"], **run.get("metrics", {}), "status": run["status"]}
        effective = run.get("effective_config", {})
        row.update(effective.get("mpc", {}))
        row["parallel_agents"] = effective.get("parallel_agents", False)
        row["source_sha256"] = run.get("provenance", {}).get("source_sha256", "unknown")
        rows.append(row)
    return pd.DataFrame(rows)


def describe(values) -> dict:
    values = np.asarray([float(v) for v in values if v is not None and np.isfinite(v)], dtype=float)
    n = len(values)
    mean = float(values.mean()) if n else None
    sd = float(values.std(ddof=1)) if n > 1 else None
    half = float(t.ppf(0.975, n - 1) * sd / np.sqrt(n)) if n > 1 else None
    return {"n": n, "mean": mean, "median": float(np.median(values)) if n else None,
            "standard_deviation": sd, "ci95_low": mean - half if half is not None else None,
            "ci95_high": mean + half if half is not None else None}


def aggregate(directory="results/runs", output="results/aggregate") -> dict:
    runs = load_runs(directory)
    if not runs:
        raise ValueError("No result records found")
    frame = run_frame(runs)
    groups = [c for c in ("algorithm", "DoD_target", "prediction_horizon", "top_l", "candidate_limit",
                          "charging_mode", "budget_mode", "iterations", "time_limit", "parallel_agents", "source_sha256") if c in frame]
    summaries = []
    for key, group in frame.groupby(groups, dropna=False, sort=True):
        meta = dict(zip(groups, key if isinstance(key, tuple) else (key,)))
        counts = {"runs": len(group), "failed_runs": int((group.status == "failed").sum()),
                  "feasible_runs": int(group.feasible.fillna(False).astype(bool).sum()),
                  "infeasible_completed_runs": int(((group.status == "completed") & ~group.feasible.fillna(False).astype(bool)).sum())}
        for metric in ("total_distance", "service_ratio", "total_planning_time", "mean_planning_time",
                       "vehicles_activated", "total_charging_time", "customers_unserved"):
            if metric not in group:
                continue
            summaries.append({**meta, **counts, "metric": metric, **describe(group[metric].dropna())})
    summary = pd.DataFrame(summaries)
    summary.to_csv(writable_path(Path(output) / "summary.csv"), index=False)
    frame.to_csv(writable_path(Path(output) / "all_runs.csv"), index=False)
    pairs = paired_differences(frame)
    pd.DataFrame(pairs).to_csv(writable_path(Path(output) / "paired_differences.csv"), index=False)
    note = {"runs": len(frame), "failed_runs": int((frame.status == "failed").sum()),
            "interval": "Student-t 95% descriptive CI; undefined for fewer than two observations",
            "pairing": "Same instance, full scenario identifier, algorithm seed, and source hash. Ambiguous duplicate configurations are reported, not cross-joined.",
            "interpretation": "Distance includes incomplete-service runs; inspect feasibility and service ratio together. No significance claims.",
            "failed_numeric_values": "Missing metrics are not imputed; n and failed_run counts are retained."}
    save_json(Path(output) / "notes.json", note)
    return note


def paired_differences(frame: pd.DataFrame, first="COORDINATED_MPC_MCTS", second="GREEDY") -> list[dict]:
    keys = ["instance", "scenario_identifier", "algorithm_seed", "source_sha256"]
    if not all(key in frame for key in keys):
        return []
    a, b = frame[frame.algorithm == first], frame[frame.algorithm == second]
    duplicates = int(a.duplicated(keys, keep=False).sum() + b.duplicated(keys, keep=False).sum())
    a = a[~a.duplicated(keys, keep=False)]
    b = b[~b.duplicated(keys, keep=False)]
    joined = a.merge(b, on=keys, how="outer", suffixes=("_a", "_b"), indicator=True)
    results = []
    for metric in ("total_distance", "service_ratio", "total_planning_time"):
        if metric + "_a" not in joined or metric + "_b" not in joined:
            continue
        matched = joined[joined._merge == "both"]
        values = (matched[metric + "_a"] - matched[metric + "_b"]).dropna()
        results.append({"first": first, "second": second, "metric": metric, "difference": "first-minus-second",
                        "matched_pairs": len(matched), "unmatched_records": int((joined._merge != "both").sum()),
                        "ambiguous_records": duplicates, **describe(values)})
    return results

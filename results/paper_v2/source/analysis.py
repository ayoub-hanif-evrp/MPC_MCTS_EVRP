"""Audited, service-first statistics with scenario-level replication."""

from pathlib import Path
import json

import numpy as np
import pandas as pd
from scipy.stats import t

from .audit import audited_records, audit_directory, result_files
from .storage import save_json, writable_path, load_json

ENVIRONMENT = ["instance", "scenario_identifier", "scenario_seed"]
FACTORS = ["prediction_horizon", "top_l", "iterations", "charging_mode", "algorithm", "parallel_agents", "DoD_target"]
METRICS = ["complete_service", "service_ratio", "customers_unserved", "vehicles_activated",
           "distance_complete", "mean_planning_time", "p95_planning_time", "maximum_planning_time",
           "total_planning_time", "nodes_expanded", "mcts_iterations", "total_charging_time", "total_charging_visits"]


def load_runs(directory):
    runs = []
    for path in result_files(directory):
        record = load_json(path)
        if "status" in record:
            runs.append(record)
    return runs


def run_frame(runs):
    rows = []
    for run in runs:
        ident = run.get("identity", {})
        row = {**run.get("metadata", {}), **run.get("metrics", {}), "status": run["status"],
               "run_id": ident.get("run_id"), "study": ident.get("study", "unknown"),
               "ablation_factor": run.get("requested_config", {}).get("ablation_factor", "baseline")}
        effective = run.get("effective_config", {})
        row.update(effective.get("mpc", {}))
        row["parallel_agents"] = effective.get("parallel_agents", False)
        row["execution_profile"] = run.get("requested_config", {}).get("execution_profile", "unspecified")
        row["source_sha256"] = run.get("provenance", {}).get("source_sha256", "unknown")
        row["distance_complete"] = row.get("total_distance") if row.get("complete_service") else None
        rows.append(row)
    return pd.DataFrame(rows)


def describe(values):
    values = np.asarray([float(v) for v in values if v is not None and np.isfinite(v)], dtype=float)
    n = len(values)
    mean = float(values.mean()) if n else None
    sd = float(values.std(ddof=1)) if n > 1 else None
    half = float(t.ppf(0.975, n - 1) * sd / np.sqrt(n)) if n > 1 else None
    return {"n": n, "mean": mean, "median": float(np.median(values)) if n else None,
            "standard_deviation": sd, "ci95_low": mean - half if half is not None else None,
            "ci95_high": mean + half if half is not None else None}


def hierarchical_summary(frame, groups):
    """Average algorithm seeds within environments before descriptive intervals."""
    rows = []
    if frame.empty:
        return pd.DataFrame(columns=groups + ["metric", "n", "mean", "median", "standard_deviation", "ci95_low", "ci95_high", "number_of_runs", "maximum_observed"])
    for key, group in frame.groupby(groups, dropna=False, sort=True):
        meta = dict(zip(groups, key if isinstance(key, tuple) else (key,)))
        for metric in METRICS:
            if metric not in group:
                continue
            environmental = group.groupby(ENVIRONMENT, dropna=False)[metric].mean()
            rows.append({**meta, "metric": metric, **describe(environmental.dropna()),
                         "number_of_runs": len(group), "contributing_runs": int(group[metric].notna().sum()),
                         "maximum_observed": group[metric].max()})
    return pd.DataFrame(rows)


def wide_summary(long):
    outcomes = ["full_service_rate", "mean_service_ratio", "median_unserved", "mean_activated_vehicles",
                "mean_distance_on_complete_runs", "median_distance_on_complete_runs", "mean_planning_time",
                "p95_planning_time", "mean_run_max_planning_time", "maximum_planning_time",
                "mean_total_planning_time", "mean_nodes_expanded", "mean_iterations", "mean_charging_time", "mean_charging_visits"]
    keys = [c for c in long.columns if c not in {"metric", "n", "mean", "median", "standard_deviation", "ci95_low", "ci95_high", "number_of_runs", "contributing_runs", "maximum_observed"}]
    if long.empty:
        return pd.DataFrame(columns=keys + ["number_of_runs"] + outcomes)
    rows = []
    for key, group in long.groupby(keys, dropna=False, sort=True):
        row = dict(zip(keys, key if isinstance(key, tuple) else (key,)))
        row["number_of_runs"] = int(group.number_of_runs.iloc[0])
        names = {"complete_service": ("full_service_rate", "mean"), "service_ratio": ("mean_service_ratio", "mean"),
                 "customers_unserved": ("median_unserved", "median"), "vehicles_activated": ("mean_activated_vehicles", "mean"),
                 "distance_complete": ("mean_distance_on_complete_runs", "mean"),
                 "mean_planning_time": ("mean_planning_time", "mean"), "p95_planning_time": ("p95_planning_time", "mean"),
                 "maximum_planning_time": ("mean_run_max_planning_time", "mean"),
                 "total_planning_time": ("mean_total_planning_time", "mean"),
                 "nodes_expanded": ("mean_nodes_expanded", "mean"), "mcts_iterations": ("mean_iterations", "mean"),
                 "total_charging_time": ("mean_charging_time", "mean"), "total_charging_visits": ("mean_charging_visits", "mean")}
        for metric, (name, stat) in names.items():
            values = group[group.metric == metric]
            row[name] = values.iloc[0][stat] if len(values) else None
        distances = group[group.metric == "distance_complete"]
        row["median_distance_on_complete_runs"] = distances.iloc[0]["median"] if len(distances) else None
        maxima = group[group.metric == "maximum_planning_time"]
        row["maximum_planning_time"] = float(maxima.iloc[0]["maximum_observed"]) if len(maxima) else None
        rows.append(row)
    return pd.DataFrame(rows)


def paired_differences(frame, first="COORDINATED_MPC_MCTS", second="GREEDY"):
    keys = ["instance", "scenario_identifier", "scenario_seed", "algorithm_seed", "source_sha256"]
    keys += [c for c in ("study", "ablation_factor") if c in frame]
    if not all(k in frame for k in keys) or "algorithm" not in frame:
        return []
    frame = frame[frame.status.eq("completed")].copy()
    if "structural_valid" in frame:
        frame = frame[frame.structural_valid]
    results = []
    study_groups = [c for c in ("study", "ablation_factor") if c in frame]
    grouped = frame.groupby(study_groups, dropna=False) if study_groups else [((), frame)]
    for study_key, subset in grouped:
        meta = dict(zip(study_groups, study_key if isinstance(study_key, tuple) else (study_key,)))
        a, b = subset[subset.algorithm == first], subset[subset.algorithm == second]
        duplicates = int(a.duplicated(keys, keep=False).sum() + b.duplicated(keys, keep=False).sum())
        a, b = a[~a.duplicated(keys, keep=False)], b[~b.duplicated(keys, keep=False)]
        joined = a.merge(b, on=keys, how="outer", suffixes=("_a", "_b"), indicator=True)
        matched = joined[joined._merge == "both"]
        for metric in ("customers_unserved", "vehicles_activated", "total_distance", "total_planning_time"):
            if metric + "_a" not in joined or metric + "_b" not in joined:
                continue
            eligible = matched
            condition = "all matched service outcomes"
            if metric == "total_planning_time" and "execution_profile_a" in eligible:
                eligible = eligible[eligible.execution_profile_a == eligible.execution_profile_b]
                condition = "matched execution profile; concurrent timings are not isolated latency"
            if metric in {"vehicles_activated", "total_distance"}:
                eligible = eligible[eligible.customers_unserved_a == eligible.customers_unserved_b]
                condition = "equal service count"
            if metric == "total_distance":
                eligible = eligible[eligible.vehicles_activated_a == eligible.vehicles_activated_b]
                condition = "equal service count and vehicle count"
            delta = eligible.assign(delta=eligible[metric + "_a"] - eligible[metric + "_b"])
            environmental = delta.groupby(ENVIRONMENT, dropna=False).delta.mean()
            results.append({**meta, "first": first, "second": second, "metric": metric,
                            "difference": "first-minus-second", "condition": condition,
                            "matched_pairs": len(matched), "eligible_pairs": len(eligible),
                            "unmatched_records": int((joined._merge != "both").sum()),
                            "ambiguous_records": duplicates, **describe(environmental.dropna())})
    return results


def aggregate(directory="results/raw", output="results/summaries"):
    runs, audits = audited_records(directory, keep_traces=False)
    if not runs:
        raise ValueError("No result records found")
    frame = run_frame(runs)
    for column in ("structural_valid", "failure_class", "reason"):
        frame[column] = [a[column] for a in audits]
    frame.to_csv(writable_path(Path(output) / "per_run.csv"), index=False)
    frame[frame.failure_class != "none"].to_csv(writable_path(Path(output) / "failures.csv"), index=False)
    good = frame[frame.structural_valid & frame.status.eq("completed") & ~frame.algorithm.isin(["STATIC_REFERENCE", "ORACLE_REFERENCE"])]
    config_groups = [c for c in ("study", "ablation_factor", "algorithm", "DoD_target", "prediction_horizon",
                     "top_l", "candidate_limit", "charging_mode", "budget_mode", "iterations", "time_limit",
                     "parallel_agents", "execution_profile", "source_sha256") if c in good]
    overall = hierarchical_summary(good, config_groups)
    family = hierarchical_summary(good, config_groups + (["instance_family"] if "instance_family" in good else []))
    overall.to_csv(writable_path(Path(output) / "summary.csv"), index=False)
    wide_summary(overall).to_csv(writable_path(Path(output) / "main_overall.csv"), index=False)
    wide_summary(family).to_csv(writable_path(Path(output) / "main_by_family.csv"), index=False)
    computation = hierarchical_summary(good, config_groups + (["number_of_customers"] if "number_of_customers" in good else []))
    computation.to_csv(writable_path(Path(output) / "computation.csv"), index=False)
    pairs = [row for other in ("GREEDY", "MPC_MCTS_H1", "INDEPENDENT_MPC_MCTS")
             for row in paired_differences(frame, second=other)]
    pd.DataFrame(pairs, columns=list(pairs[0]) if pairs else ["first", "second", "metric", "mean", "n"]).to_csv(
        writable_path(Path(output) / "paired_comparisons.csv"), index=False)
    for factor in FACTORS:
        source_factor = {"top_l": "top_L", "iterations": "mcts_iterations", "DoD_target": "dynamicity"}.get(factor, factor)
        subset = good[(good.study == "ablations") & good.ablation_factor.isin(["baseline", source_factor])]
        hierarchical_summary(subset, config_groups).to_csv(writable_path(Path(output) / f"ablation_{factor}.csv"), index=False)
    audit_directory(directory, output)
    note = dict(runs=len(frame), failed_runs=int(frame.status.eq("failed").sum()),
                structural_failures=int((~frame.structural_valid).sum()),
                incomplete_runs=int(frame.failure_class.eq("incomplete_service").sum()),
                replication="Algorithm seeds averaged within instance/scenario; descriptive Student-t 95% CI across scenarios. CI undefined for n<2. Scenarios of the same instance may still be correlated.",
                interpretation="Service first. Distance conditional on complete service; paired distance requires equal service and vehicle counts. Vehicle marginals are descriptive, not rankings. No significance claims.",
                latency="p95_planning_time summaries average within-run decision-latency p95; not a pooled percentile.")
    save_json(Path(output) / "notes.json", note)
    return note


def export_tables(directory="results/summaries", output="results/tables"):
    directory = Path(directory)
    audit = pd.read_csv(directory / "audit_report.csv")
    if "structural_valid" not in audit:
        raise ValueError("Run aggregate/audit before exporting tables")
    names = ["reference_validation", "main_by_family", "main_overall", "paired_comparisons", "computation", "failures"]
    names += [f"ablation_{factor}" for factor in FACTORS]
    paths = []
    for name in names:
        path = directory / f"{name}.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if name == "reference_validation":
            columns = ["instance", "published_vehicles", "our_vehicles", "vehicle_match", "published_distance",
                       "our_distance", "distance_gap_percent", "validation_status"]
        elif name == "failures":
            columns = ["study", "instance", "scenario_identifier", "algorithm", "scenario_seed", "algorithm_seed",
                       "failure_class", "customers_unserved", "reason"]
        elif name == "paired_comparisons":
            columns = ["study", "first", "second", "metric", "condition", "matched_pairs", "eligible_pairs", "n",
                       "mean", "median", "standard_deviation", "ci95_low", "ci95_high", "ambiguous_records", "unmatched_records"]
        elif name == "computation":
            frame = wide_summary(frame)
            columns = ["study", "DoD_target", "number_of_customers", "algorithm", "mean_planning_time",
                       "p95_planning_time", "maximum_planning_time", "mean_nodes_expanded", "mean_iterations", "number_of_runs"]
        else:
            if name.startswith("ablation_"):
                frame = wide_summary(frame)
            columns = ["study", "instance_family", "DoD_target", "algorithm"]
            if name.startswith("ablation_"):
                columns += [name.removeprefix("ablation_"), "ablation_factor"]
            columns += ["full_service_rate", "mean_service_ratio", "median_unserved", "mean_activated_vehicles",
                        "mean_distance_on_complete_runs", "median_distance_on_complete_runs", "mean_planning_time",
                        "p95_planning_time", "number_of_runs"]
        frame = frame[[c for c in dict.fromkeys(columns) if c in frame]].copy()
        for column in frame.select_dtypes(include="number"):
            precision = 6 if "planning_time" in column else 2 if "distance" in column or "vehicles" in column else 3
            frame[column] = frame[column].round(precision)
        frame.to_csv(writable_path(Path(output) / "csv" / path.name), index=False)
        display = frame.copy()
        for column in display:
            if "planning_time" in column:
                display[column] = display[column].map(lambda value: "--" if pd.isna(value) else f"{1000*value:.1f} ms" if value < 1 else f"{value:.2f} s")
            if column == "scenario_identifier":
                display[column] = display[column].astype(str).str[:12]
        display = display.rename(columns={"number_of_customers": "Customers", "number_of_runs": "Runs",
            "full_service_rate": "Full service", "mean_service_ratio": "Service mean", "median_unserved": "Unserved median",
            "mean_activated_vehicles": "EV mean", "mean_distance_on_complete_runs": "D mean (complete)",
            "median_distance_on_complete_runs": "D median (complete)", "mean_planning_time": "Latency mean",
            "p95_planning_time": "Latency p95 mean", "maximum_planning_time": "Latency max",
            "mean_nodes_expanded": "Nodes mean", "mean_iterations": "Iterations mean"})
        latex = display.to_latex(index=False, escape=True, float_format=lambda x: f"{x:.3f}", na_rep="--")
        latex = "\\begin{sidewaystable}\n\\centering\n\\scriptsize\n\\resizebox{\\linewidth}{!}{%\n" + latex + "}\n\\end{sidewaystable}\n"
        destination = writable_path(Path(output) / "latex" / f"{name}.tex")
        destination.write_text(latex, encoding="utf-8")
        paths.append(str(destination))
    return paths

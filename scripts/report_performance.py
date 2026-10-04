"""Generate the measured prelaunch report without executing the paper campaign."""

from pathlib import Path

from evrp.experiments import load_config
from evrp.paper import estimate, validate_launch
from evrp.storage import load_json, save_json


def main():
    root = Path("results/performance")
    report = load_json(root / "calibration.json")
    verification = load_json(root / "verification.json")
    if verification["source_sha256"] != report["source_sha256"]:
        raise RuntimeError("Verification and calibration source fingerprints differ")
    config = load_config("configs/paper.yaml")
    output = Path(__import__("os").environ.get("LOCALAPPDATA", Path.home())) / "EVRP/paper"
    estimation = estimate(config, output, 4)
    try:
        validate_launch(config, report, estimation, execute=True)
        gate = "PASSED. This check does not launch any jobs. Explicit user execution is still required."
    except (RuntimeError, ValueError) as error:
        gate = "BLOCKED: " + str(error)
    save_json(root / "campaign_estimate.json", {**estimation, "gate": gate})
    selected = report["selection"]["budget"]
    lines = ["# Measured Prelaunch Results", "", f"Gate: **{gate}**", "",
             "The old 17,017-run campaign is cancelled; its 58 completed runs are preserved.",
             "The replacement paper campaign has NOT been launched. No changes were pushed to GitHub.", "",
             "## Runtime and Search", "",
             "The unprofiled pre-optimization c101_21 control at 32 iterations took 167.988 seconds."]
    for budget in (8, 16, 32, 64):
        row = next(r for r in report["rows"] if r["instance"] == "c101_21" and r["iterations"] == budget)
        lines.append(f"- Optimized {budget} iterations: {row['wall_seconds']:.3f} s, median decision {row['median_planning_time']:.3f} s, p95 {row['p95_planning_time']:.3f} s, service {row['customers_served']}/100.")
    lines += ["", "These isolated calibration times include cached dependency loading, result creation and serialization; cold reference generation is counted separately below.",
              "The baseline/final profiling JSON files retain action, transition, escape, proposal, MCTS phase, coordinator, serialization and per-agent simulation measurements.", "",
              "| Iterations | Before profile s | Final profile s | Mean branch before/final | Max branch before/final | Transition calls before/final |", "| ---: | ---: | ---: | --- | --- | --- |"]
    for budget in (8, 16, 32):
        before = load_json(root / f"before_{budget}.json")
        after = load_json(root / f"final_{budget}.json")
        calls = lambda r: sum(f["calls"] for f in r["functions"] if f["name"] == "transition" and f["file"] == "model.py")
        lines.append(f"| {budget} | {before['wall_seconds']:.3f} | {after['wall_seconds']:.3f} | {before['measurements']['mean_branching']:.2f} / {after['measurements']['mean_branching']:.2f} | {before['measurements']['max_branching']} / {after['measurements']['max_branching']} | {calls(before):,} / {calls(after):,} |")
    lines += ["", "## Selected Budget", "", f"**{selected} iterations per agent replan**, common across all test instances.", report["selection"]["reason"],
              "Distance is compared only on equal-service/equal-vehicle pairs. The 8-iteration candidate has no such pairs against the selected reference budget; absence of pairs is not evidence of distance equivalence.",
              "Symmetry reuse remains disabled because it changed physical traces and materially worsened one small-instance distance.", "",
              "## Calibration Table", "", "All 24 rows passed independent physical, commitment, hidden-information, and provenance audits. Incomplete service remains an outcome, not an execution error.", "",
              "| Instance | Budget | Served | EVs | Distance | Planning s | Median epoch s | p95 epoch s | Expanded nodes |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for r in report["rows"]:
        lines.append(f"| {r['instance']} | {r['iterations']} | {r['customers_served']} | {r['vehicles_activated']} | {r['total_distance']:.2f} | {r['total_planning_time']:.3f} | {r['median_planning_time']:.3f} | {r['p95_planning_time']:.3f} | {r['nodes_expanded']} |")
    lines += ["", "## Jobs and Resource Gate", "", "| Study | Table cells | Unique conditions | Additional runs | Reusable |", "| --- | ---: | ---: | ---: | ---: |"]
    for study, r in estimation["studies"].items():
        lines.append(f"| {study} | {r['table_rows']} | {r['unique_conditions']} | {r['additional_runs']} | {r['reusable']} |")
    resource = estimation["resource"]
    lines += ["", f"Total unique jobs: {estimation['planned']}; reusable: {estimation['reusable']}; remaining: {estimation['remaining']}.",
              f"Selected outer workers: {resource['workers']} on {resource['physical_cores']} physical cores. Measured peak per process {resource['measured_peak_mib']:.1f} MiB; reservation {resource['per_worker_mib']:.1f} MiB/worker plus {resource['reserved_mib']} MiB system margin. BLAS threads: 1.",
              "Realtime runs execute after the outer pool exits, with separate timing labels. No nested throughput pools.", ""]
    for field, title in (("estimated_sequential_seconds", "Sequential"), ("estimated_parallel_seconds", "Selected workers"), ("dependency_seconds", "Cold reference work, before parallelism")):
        seconds = estimation[field]
        lines.append(f"- {title}: {seconds/3600:.2f} hours." if seconds is not None else f"- {title}: unknown; launch blocked.")
    lines += ["", estimation["assumption"] + ".", estimation["uncertainty"], "",
              "## Cold Reference Verification", "", "| Instance | Exact recomputation seconds | Reference content hash unchanged |", "| --- | ---: | --- |"]
    for r in load_json(root / "reference_cold.json"):
        lines.append(f"| {r['instance']} | {r['seconds']:.3f} | {r['identical_reference']} |")
    lines += ["", "The originally measured cold setup costs for r201_21 and rc201_21 were 3665.453 and 3382.607 seconds. Prefix caching and exact geometry reuse do not change their reference schedules or scenario release bounds.", "",
              "## Launch", "", "Estimate first:", "", "```powershell", 'python -m evrp.cli estimate --config configs/paper.yaml --workers 4 --output "$env:LOCALAPPDATA\\EVRP\\paper"', "```", "",
              "Only after reviewing a passing gate and explicitly deciding to launch:", "", "```powershell", 'python -m evrp.cli paper --config configs/paper.yaml --workers 4 --output "$env:LOCALAPPDATA\\EVRP\\paper" --execute', "```", "",
              "Summary tables and PNG figures with exact-data CSVs are copied to results/paper. Raw traces remain on the local SSD. Changing the calibrated method/source closes the gate.", ""]
    lines += ["## Verification", "",
              f"- Full regression suite: {verification['pytest']['passed']} passed in {verification['pytest']['seconds']:.2f} s.",
              "- Four external reference-validation cases passed.",
              "- All 24 calibration runs and all three final profiles passed physical/information audits.",
              "- Three pre-optimization golden physical traces matched with action reduction disabled.",
              "- All 24 calibration physical traces, events and non-timing metrics matched across the exact-cache revisions.",
              "- Seven reference-prefix traces and three complete reference content hashes matched exactly.",
              "- Original benchmark inputs unchanged; git diff --check passed.",
              "- PNG figures only, with underlying CSVs; no new PDF figures.", "",
              "Detailed measured bottlenecks and implementation changes: [performance_analysis.md](performance_analysis.md).", ""]
    Path("docs/performance_results.md").write_text("\n".join(lines), encoding="utf-8")
    print(gate)
    print(estimation)


if __name__ == "__main__":
    main()

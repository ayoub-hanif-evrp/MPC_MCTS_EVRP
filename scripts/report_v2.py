"""Study-specific, service-first diagnostic presentation. No experiment execution."""

import os
os.environ.setdefault("MPLBACKEND", "Agg")
from pathlib import Path
from collections import Counter
import hashlib
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import t

from evrp.audit import audit_record
from evrp.instance import load_instance
from evrp.storage import BENCHMARK, load_json, save_json

OUT = Path("results/paper_v2")
FAMILIES = ["C1", "C2", "R1", "R2", "RC1", "RC2"]
LABELS = {"GREEDY": "Greedy", "MPC_MCTS_H1": "MPC-MCTS-H1",
          "INDEPENDENT_MPC_MCTS": "Independent", "COORDINATED_MPC_MCTS": "Coordinated"}
ORDER = ["Greedy", "Independent", "Coordinated"]
COLORS = {"Greedy": "#737373", "Independent": "#21855b", "Coordinated": "#326eae"}


def markdown(frame):
    def cell(value):
        if pd.isna(value):
            return "NA"
        if isinstance(value, (float, np.floating)):
            return f"{value:.3f}" if abs(value) < 1 else f"{value:.2f}"
        return str(value).replace("|", "/")
    return "\n".join(["| " + " | ".join(map(str, frame.columns)) + " |",
                      "| " + " | ".join(["---"]*len(frame.columns)) + " |"] +
                     ["| " + " | ".join(cell(x) for x in row) + " |" for row in frame.itertuples(index=False, name=None)])


def table(name, frame, note=""):
    for directory in ("csv", "latex", "markdown"):
        (OUT/"tables"/directory).mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT/"tables/csv"/(name+".csv"), index=False)
    (OUT/"tables/latex"/(name+".tex")).write_text(frame.to_latex(index=False, escape=True, float_format="%.3f"), encoding="utf-8")
    content = markdown(frame) + ("\n\n"+note if note else "") + "\n"
    (OUT/"tables/markdown"/(name+".md")).write_text(content, encoding="utf-8")
    return content


def interval(values):
    x = np.asarray(values, dtype=float)
    avg = float(x.mean())
    half = float(t.ppf(.975, len(x)-1)*x.std(ddof=1)/np.sqrt(len(x))) if len(x) > 1 else np.nan
    return avg, half


def outcomes(frame):
    return dict(Service_pct=100*frame.service_ratio.mean(), Unserved=frame.customers_unserved.mean(),
                EVs=frame.vehicles_activated.mean(), Distance=frame.total_distance.mean(),
                Planning_s=frame.total_planning_time.mean())


def paired(a, b, prefix):
    keys = ["instance", "DoD", "scenario_identifier"]
    pair = a.merge(b, on=keys, suffixes=("_a", "_b"), validate="one_to_one")
    rows = []
    for r in pair.itertuples():
        equal_service = r.customers_served_a == r.customers_served_b
        equal_evs = r.vehicles_activated_a == r.vehicles_activated_b
        rows.append(dict(Instance=r.instance, Family=r.family_a, DoD=r.DoD, Comparison=prefix,
            Delta_unserved=r.customers_unserved_a-r.customers_unserved_b,
            Delta_EV=r.vehicles_activated_a-r.vehicles_activated_b if equal_service else np.nan,
            Delta_distance=r.total_distance_a-r.total_distance_b if equal_service and equal_evs else np.nan,
            Distance_pct=100*(r.total_distance_a/r.total_distance_b-1) if equal_service and equal_evs else np.nan,
            equal_service=equal_service, equal_EVs=equal_evs))
    return pd.DataFrame(rows)


def main():
    manifest = load_json(OUT/"diagnostic_manifest.json")
    if manifest["status"] != "completed":
        raise RuntimeError("Diagnostic campaign is not complete")
    records, rows, index = {}, [], []
    for item in manifest["records"]:
        raw = load_json(item["path"])
        errors = audit_record(raw)
        if raw["status"] != "completed" or errors:
            raise RuntimeError(f"Invalid diagnostic record: {item['path']}: {errors}")
        if raw["provenance"]["source_sha256"] != manifest["source_sha256"]:
            raise RuntimeError("Mixed scientific revisions in diagnostic report")
        oracle = raw["metadata"]["algorithm"] == "ORACLE_REFERENCE"
        target = OUT/("oracle_raw" if oracle else "raw")/Path(item["path"]).name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item["path"], target)
        digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
        if digest(target) != digest(item["path"]):
            raise RuntimeError("Diagnostic archive copy mismatch")
        index.append(dict(key=item["key"], path=target.as_posix(), sha256=digest(target)))
        records[item["key"]] = raw
        meta, cfg = raw["metadata"], raw["requested_config"]
        rows.append(dict(key=item["key"], instance=meta["instance"], family=meta["instance_family"],
            algorithm=LABELS.get(meta["algorithm"], "Offline feasibility oracle"), DoD=meta["DoD_target"],
            scenario_identifier=meta["scenario_identifier"], K_ref=meta["K"], budget=cfg["mcts_iterations"],
            horizon=cfg["prediction_horizon"], fleet=cfg["fleet_mode"], execution_profile=cfg["execution_profile"],
            **raw["metrics"], **raw.get("diagnostics", {}).get("summary", {})))
    pd.DataFrame(index).to_csv(OUT/"raw_index.csv", index=False)
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT/"all_diagnostic_runs.csv", index=False)
    membership = pd.DataFrame(manifest["memberships"])
    def phase(name):
        keys = set(membership.loc[membership.phase == name, "key"])
        return frame[frame.key.isin(keys)].copy()
    main_runs, calibration, fixed, horizon, oracle = map(phase, ("main", "calibration", "fleet_control", "horizon", "oracle"))
    if len(main_runs) != 36 or len(oracle) != 12:
        raise RuntimeError("Incomplete requested comparison grid")
    dynamic = main_runs[main_runs.DoD == .5]
    coordinated = main_runs[main_runs.algorithm == "Coordinated"]
    selected_dynamic = coordinated[coordinated.DoD == .5]
    horizon = pd.concat([horizon, selected_dynamic]).drop_duplicates("key")
    captions, figure_links = [], {}
    plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "axes.spines.top": False,
                         "axes.spines.right": False})

    def figure(study, name, fig, data, caption):
        if data.empty:
            plt.close(fig)
            return
        folder = OUT/"figures"/study
        folder.mkdir(parents=True, exist_ok=True)
        stem = folder/name
        fig.tight_layout()
        fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
        fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
        data.to_csv(folder/(name+"_data.csv"), index=False)
        plt.close(fig)
        link = f"![{name.replace('_', ' ')}](figures/{study}/{name}.png)"
        figure_links[name] = link
        captions.append(f"## {name}\n\n{caption}\n\n{link}\n")

    family_rows = []
    for family in FAMILIES+["Overall"]:
        subset = dynamic if family == "Overall" else dynamic[dynamic.family == family]
        for algorithm in ORDER:
            group = subset[subset.algorithm == algorithm]
            family_rows.append(dict(Family=family, Algorithm=algorithm, n=len(group), **outcomes(group)))
    main_table = table("main_by_family", pd.DataFrame(family_rows),
        "DoD=.5. One development instance per family; Overall is six instances per method. Distance/EV means are descriptive, never ranked ahead of service. No bold winners or significance claims.")
    static_table = table("static_sanity", pd.DataFrame([dict(Instance=r.instance, Algorithm=r.algorithm,
        Served=r.customers_served, Unserved=r.customers_unserved, K_ref=r.K_ref, EVs=r.vehicles_activated,
        Distance=r.total_distance, Planning_s=r.total_planning_time)
        for r in main_runs[main_runs.DoD == 0].itertuples()]))
    fig, ax = plt.subplots(figsize=(9, 4))
    for j, algorithm in enumerate(ORDER):
        group = dynamic[dynamic.algorithm == algorithm].set_index("family").loc[FAMILIES]
        ax.bar(np.arange(6)+(j-1)*.24, 100*group.service_ratio, width=.23, color=COLORS[algorithm], label=algorithm)
    ax.set(xticks=np.arange(6), xticklabels=FAMILIES, ylabel="Customers served (%)", ylim=(0, 105),
           title="Development diagnostics: dynamic service by family")
    ax.legend(ncol=3, loc="lower center")
    figure("main", "service_by_family", fig, dynamic,
        "Service at DoD=.5 for three online algorithms, six development instances (18 runs). Each family has n=1 per method, so no error bars are identifiable. No distance comparison. Timings in source CSV are concurrent diagnostics, not isolated realtime measurements.")

    dyn_rows = []
    for algorithm in ORDER:
        for dod in (0., .5):
            g = main_runs[(main_runs.algorithm == algorithm) & (main_runs.DoD == dod)]
            avg, half = interval(100*g.service_ratio)
            dyn_rows.append(dict(Algorithm=algorithm, DoD=dod, n=len(g), Service_pct=avg, CI_half_width=half,
                                 EVs=g.vehicles_activated.mean(), Planning_s=g.total_planning_time.mean()))
    dynamicity_table = table("dynamicity", pd.DataFrame(dyn_rows),
        "95% Student-t descriptive intervals across six heterogeneous development instances, not seed-level or population uncertainty. Only DoD 0 and .5 were tested.")
    fig, ax = plt.subplots(figsize=(7, 4))
    for algorithm in ORDER:
        g = pd.DataFrame(dyn_rows).query("Algorithm == @algorithm")
        ax.errorbar(g.DoD, g.Service_pct, yerr=g.CI_half_width, marker="o", capsize=4, label=algorithm, color=COLORS[algorithm])
    ax.set(xlabel="Degree of dynamism", ylabel="Customers served (%)", xticks=[0,.5], title="Static and dynamic controls")
    ax.legend()
    figure("dynamicity", "static_dynamic_service", fig, pd.DataFrame(dyn_rows),
        "Mean service at two DoDs, n=6 instances per method/DoD (36 runs). Error bars are untruncated 95% descriptive Student-t intervals across instance means and may extend outside physical percentage bounds. Same paired instances and seeds; not a dense dynamicity sweep. No distance comparison; concurrent diagnostic execution.")
    comparison = []
    for family in FAMILIES:
        g = coordinated[coordinated.family == family].set_index("DoD")
        a, b = g.loc[0.], g.loc[.5]
        same_service = a.customers_served == b.customers_served
        eligible = same_service and a.vehicles_activated == b.vehicles_activated
        comparison.append(dict(Family=family, Static_service=100*a.service_ratio, Dynamic_service=100*b.service_ratio,
            Static_EVs=a.vehicles_activated, Dynamic_EVs=b.vehicles_activated,
            Delta_EV_pct=100*(b.vehicles_activated/a.vehicles_activated-1) if same_service else np.nan,
            Static_distance=a.total_distance, Dynamic_distance=b.total_distance,
            Delta_distance_pct=100*(b.total_distance/a.total_distance-1) if eligible else np.nan))
    table("static_dynamic", pd.DataFrame(comparison), "Coordinated only. EV deltas require equal service; distance deltas additionally require equal EV count. NA denotes ineligible, not zero improvement.")

    pairs = paired(coordinated, main_runs[main_runs.algorithm == "Independent"], "Coordinated - Independent")
    pair_table = table("paired_methods", pairs, "Unserved deltas use all paired conditions. EV deltas require equal service. Distance deltas and percentages require equal service AND equal EV count. Negative unserved means higher coordinated service.")
    forest = []
    p = pairs[pairs.DoD == .5]
    for family in FAMILIES+["Overall"]:
        g = p if family == "Overall" else p[p.Family == family]
        avg, half = interval(g.Delta_unserved)
        forest.append(dict(Family=family, n=len(g), Mean_delta_unserved=avg, CI_half_width=half))
    forest = pd.DataFrame(forest)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.axvline(0, color=".6", linewidth=1)
    for y, r in enumerate(forest.itertuples()):
        ax.errorbar(r.Mean_delta_unserved, y, xerr=r.CI_half_width if r.n > 1 else None, fmt="o", color=COLORS["Coordinated"], capsize=4)
    ax.set(yticks=range(7), yticklabels=forest.Family, xlabel="Coordinated minus Independent: unserved customers", title="Paired coordination diagnostic (DoD=.5)")
    ax.invert_yaxis()
    figure("main", "coordination_differences", fig, forest,
        "Paired difference in unserved customers on six identical scenarios at DoD=.5. Each family has one pair (no interval); Overall has six pairs with a 95% descriptive Student-t interval. Negative favors coordination on service only. No fleet/distance superiority inferred. Concurrent diagnostic timing context.")

    fleet_rows = []
    v1 = pd.read_csv("results/paper_v1_fixed_fleet/A/summaries/per_run.csv")
    for r in selected_dynamic.itertuples():
        hard = fixed[fixed.instance == r.instance].iloc[0]
        old = v1[(v1.instance == r.instance) & (v1.algorithm == "COORDINATED_MPC_MCTS")].iloc[0]
        if hard.scenario_identifier != r.scenario_identifier or old.scenario_identifier != r.scenario_identifier:
            raise RuntimeError("Fleet comparison scenario mismatch")
        fleet_rows.append(dict(Instance=r.instance, K_ref=r.K_ref, V1_served=old.customers_served,
            V2_hard_served=hard.customers_served, V2_reserve_served=r.customers_served,
            Hard_EVs=hard.vehicles_activated, Reserve_EVs=r.vehicles_activated,
            Extra_EVs=max(0,r.vehicles_activated-r.K_ref), Hard_distance=hard.total_distance,
            Reserve_distance=r.total_distance, Hard_planning_s=hard.total_planning_time,
            Reserve_planning_s=r.total_planning_time))
    fleet_table = table("fleet_diagnostic", pd.DataFrame(fleet_rows),
        "Same scenarios/seeds. V2 hard/flexible runs share the selected budget and coverage/wait rules; flexible treatment also changes reserve proposal sharing and busy-tail coverage, so it is a fleet-policy comparison, not a cap-only causal estimate. V1 uses budget16 and different search/wait rules; its column is descriptive provenance only.")

    ablations = []
    for factor, subset, x in [("Horizon", horizon, "horizon"), ("Budget", calibration, "budget")]:
        stats = []
        for value, g in subset.groupby(x):
            avg, half = interval(100*g.service_ratio)
            latency, latency_half = interval(g.p95_planning_time)
            row = dict(Factor=factor, Value=value, n=len(g), Service_pct=avg, Service_CI_half=half,
                EVs=g.vehicles_activated.mean(), Mean_actual_simulations_per_search=(g.mcts_iterations/g.agent_replans).mean(),
                p95_epoch_s=latency, Latency_CI_half=latency_half,
                Planning_s=g.total_planning_time.mean())
            stats.append(row)
            ablations.append(row)
        data = pd.DataFrame(stats)
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].errorbar(data.Value, data.Service_pct, yerr=data.Service_CI_half, marker="o", capsize=4, color=COLORS["Coordinated"])
        axes[1].errorbar(data.Value, data.p95_epoch_s, yerr=data.Latency_CI_half, marker="s", capsize=4, color="#9d503f")
        for ax in axes:
            ax.set_xlabel("Prediction horizon" if factor == "Horizon" else "Nominal total simulations (root-coverage floor)")
            ax.set_xticks(data.Value)
        axes[0].set_ylabel("Customers served (%)")
        axes[1].set_ylabel("Mean within-run p95 epoch latency (s)")
        figure("ablations", factor.lower()+"_tradeoff", fig, data,
            f"Coordinated {factor.lower()} diagnostic at DoD=.5, n=6 development instances per setting (18 conditions). Other online settings fixed, except the chosen horizon/budget factor. Error bars are 95% descriptive Student-t intervals across instances. Actual simulations include mandatory root coverage; latency includes concurrent machine contention and is not an isolated realtime guarantee. No distance panel.")
    ablation_table = table("ablations", pd.DataFrame(ablations), "Only horizon and MCTS-budget factors measured in V2. Top-L remains3 and charging is partial; no evidence for their comparative superiority is claimed.")
    runtime = main_runs.groupby(["algorithm","DoD"]).agg(Runs=("key","count"), Mean_run_planning_s=("total_planning_time","mean"),
        Mean_epoch_s=("mean_planning_time","mean"), Mean_run_p95_s=("p95_planning_time","mean"),
        Max_epoch_s=("maximum_planning_time","max"), Mean_simulations=("mcts_iterations","mean")).reset_index()
    runtime_table = table("runtime", runtime, "All online measurements are concurrent diagnostics, outer workers only, BLAS threads1. Mean run p95 is not a pooled p95. Observer/audit/serialization time is excluded from planning time. No V2 realtime experiment was run.")
    from scripts.analyze_v2_waits import main as analyze_waits
    analyze_waits()
    oracle_table = table("reference_validation", oracle[["instance","DoD","customers_served","K_ref","total_distance","final_return_feasibility"]],
        "OFFLINE FEASIBILITY ORACLE. Replays the reference that generated each scenario. Contains future route information; never an online competitor. All12 independently audited for released-before-dispatch and physical replay.")

    unserved, counters = [], []
    for r in main_runs.itertuples():
        raw = records[r.key]
        for customer in raw["diagnostics"]["unserved"]:
            unserved.append({"algorithm":r.algorithm, "run_key":r.key, **customer})
        counters.append(dict(Instance=r.instance, Algorithm=r.algorithm, DoD=r.DoD,
                             **raw["diagnostics"]["summary"]))
    pd.DataFrame(unserved).to_csv(OUT/"unserved_customers.csv", index=False)
    table("decision_diagnostics", pd.DataFrame(counters), "Read-only sampled direct next-service feasibility, not an exhaustive charging-route oracle. 'Last feasible' is the last observed decision epoch, not an analytic time bound.")
    reason_counts = pd.DataFrame([dict(Reason=k, Customers=v) for k,v in Counter(r["final_reason"] for r in unserved).items()], columns=["Reason","Customers"])
    reasons_table = table("unserved_reasons", reason_counts, "Heuristic evidence labels, not exclusive causal proofs. Full per-customer rows retain sampled feasibility, candidate/top-L/intent counts and physical failure types.")
    all_unserved = []
    for key, raw in records.items():
        for row in raw.get("diagnostics", {}).get("unserved", []):
            all_unserved.append(dict(run_key=key, algorithm=raw["metadata"]["algorithm"],
                budget=raw["requested_config"]["mcts_iterations"], fleet=raw["requested_config"]["fleet_mode"],
                horizon=raw["requested_config"]["prediction_horizon"], **row))
    pd.DataFrame(all_unserved).to_csv(OUT/"all_diagnostic_unserved_customers.csv", index=False)

    appendix_columns = ["instance","family","algorithm","DoD","customers_served","customers_unserved","vehicles_activated",
                        "total_distance","total_charging_visits","total_charging_time","mean_planning_time","p95_planning_time"]
    appendix = main_runs[appendix_columns].sort_values(["instance","DoD","algorithm"])
    (OUT/"PER_INSTANCE_RESULTS.md").write_text("# Per-Instance Diagnostic Results\n\nOnly the six development instances, not the full paper benchmark. Timing is concurrent.\n\n"+
        markdown(appendix)+"\n\n## Paired Appendix\n\n"+pair_table+
        "\n## Horizon and Budget Detail\n\n"+markdown(pd.concat([horizon,calibration]).drop_duplicates("key")[["instance","horizon","budget","customers_served","vehicles_activated","total_distance","total_planning_time"]])+"\n", encoding="utf-8")

    # Pre-specified qualitative choice; do not cherry-pick a successful substitute.
    representative = coordinated[(coordinated.instance == "c101_21") & (coordinated.DoD == .5)].iloc[0]
    if representative.complete_service:
        representative_figures(records[representative.key], figure)

    static_co = coordinated[coordinated.DoD == 0]
    question_rows = [dict(Question="Oracle complete service?", Answer=f"{int(oracle.complete_service.sum())}/12 complete"),
        dict(Question="Coordinated static complete service?", Answer=f"{int(static_co.complete_service.sum())}/6 complete; mean service {100*static_co.service_ratio.mean():.2f}%"),
        dict(Question="Flexible fleet improves service?", Answer=f"Mean paired gain {np.mean([r['V2_reserve_served']-r['V2_hard_served'] for r in fleet_rows]):.2f} customers at DoD=.5; mechanism is not a cap-only ablation"),
        dict(Question="Extra dynamic vehicles?", Answer=f"Mean {np.mean([r['Extra_EVs'] for r in fleet_rows]):.2f} beyond K_ref"),
        dict(Question="Coordination improves service?", Answer=f"Mean coordinated-minus-independent unserved {pairs.Delta_unserved.mean():.2f} across12 paired controls; inspect family rows"),
        dict(Question="Root actions evaluated?", Answer=f"Coverage min {main_runs[main_runs.algorithm != 'Greedy'].root_action_coverage.min():.3f}; minimum root visits {int(main_runs[main_runs.algorithm != 'Greedy'].minimum_root_visits.min())}"),
        dict(Question="V2 full campaign authorized?", Answer="NO. Scientific review required; executor blocked.")]
    gate_table = table("scientific_gate", pd.DataFrame(question_rows))
    setup = f"Six development instances, DoD 0/.5, scenario/algorithm seeds0, partial charging, Hp5, L3, customer/station/target limits12/4/5. Selected nominal MCTS budget **{manifest['selection']['budget']}**, mandatory root coverage charged to actual simulations. {manifest['resource']['workers']} outer workers; concurrent timings, BLAS1. {len(frame)-len(oracle)} unique online diagnostics plus12 offline controls. No V2 all-56-instance campaign, seed-robustness study or realtime run."
    limitations = ("These are development diagnostics, not final paper results. Six heterogeneous instances and one seed cannot establish superiority or generalization. "
        "A successful service outcome obtained by many reserve routes is not a good fleet/distance solution. Busy-tail coverage is optimistic, not binding; reserve sharing, root coverage and wait semantics change the method. "
        "Fixed-versus-flexible is a fleet-policy comparison; V1-versus-V2 is additionally confounded by budget and search changes. Diagnostics sample direct service opportunities and cannot prove every charging-mediated cause of loss. "
        "Concurrent timings must not be represented as isolated realtime latency. Main V2 breadth, full charging, L sweeps and repeated seeds remain unmeasured. The full paper campaign is blocked pending review.")
    worst = coordinated.loc[coordinated.total_planning_time.idxmax()]
    blocked = (f"**Scientific and computational gate FAILED.** The mechanical calibration rule selected{manifest['selection']['budget']} simulations, "
        f"but that is not an accepted final configuration. Worst coordinated diagnostic: {worst.instance}, DoD={worst.DoD:g}, "
        f"{worst.total_planning_time:.2f}s ({worst.total_planning_time/60:.2f}min) planning and{int(worst.wait_selected):,} WAIT selections. "
        "Repeated short WAITs can still create long idle spells despite the per-action bound. See the [idle-spell audit](tables/markdown/idle_spells.md). "
        "The coordinated method also misses customers that Independent serves and uses far more EVs than the reference. Do not launch a full campaign or claim a final budget.")
    sections = ["# V2 Diagnostic Results: Not Final Paper Results", "", "**STOPPED AFTER THE DIAGNOSTIC CAMPAIGN. Full paper execution is blocked pending user review.**", "", blocked,
        "## Experimental Setup", setup, "", "## Scientific Gate", gate_table,
        "## Offline Feasibility Control", oracle_table,
        "## Main Benchmark Results", "This is the six-case dynamic diagnostic subset, not a new56-instance benchmark.", main_table, figure_links["service_by_family"],
        "## Static Sanity", static_table,
        "## Fleet Diagnosis", fleet_table,
        "## Dynamicity Analysis", dynamicity_table, figure_links["static_dynamic_service"],
        "[Conditioned static/dynamic table](tables/markdown/static_dynamic.md). Only two DoD levels are measured.",
        "## Coordination Analysis", "Full paired differences and eligibility are in [paired methods](tables/markdown/paired_methods.md).", figure_links["coordination_differences"],
        "## MPC Horizon Analysis", figure_links["horizon_tradeoff"],
        "## MCTS-Budget Analysis", "The quality-only rule chose96 through its reference tie-break and conditioned distance test. That outcome fails the practical runtime/fleet gate. Budget32 achieved similar service with substantially lower runtime; it is a candidate for further bounded algorithm diagnosis, not a validated paper setting.", ablation_table, figure_links["budget_tradeoff"],
        "## Top-L and Partial-vs-Full Charging", "Not rerun in V2. L=3 and partial charging were held fixed. Archived V1 ablations remain diagnostic only. No empty comparison plot or unsupported charging-improvement claim is produced.",
        "## Realtime/Computational Performance", runtime_table,
        "V2 wall-clock experiments are deferred. Mandatory root coverage can exceed a nominal deadline; a dedicated isolated test is required before any realtime claim.",
        "## Representative Trajectory", "Pre-specified c101_21, DoD=.5, Coordinated, seeds0. Complete service does not imply fleet efficiency.",
        figure_links.get("representative_routes", "The pre-specified run is incomplete, so no successful-route figure is presented."),
        figure_links.get("representative_evolution", ""),
        "## Unserved Customers", reasons_table,
        "[All diagnostic customer-level reasons](all_diagnostic_unserved_customers.csv); [main-grid reasons](unserved_customers.csv). Counts are by sampled customer/run, not independent observations.",
        "## Limitations", limitations,
        "## Details", "[Per-instance appendix](PER_INSTANCE_RESULTS.md) | [Figure captions](FIGURE_CAPTIONS.md) | [Diagnostic counters](tables/markdown/decision_diagnostics.md) | [Root coverage](tables/markdown/root_coverage.md) | [Raw archive index](raw_index.csv)", ""]
    (OUT/"PAPER_RESULTS.md").write_text("\n\n".join(sections).rstrip() + "\n", encoding="utf-8")
    (OUT/"FIGURE_CAPTIONS.md").write_text("# Diagnostic Figure Captions\n\nAll figures are preliminary diagnostics, with PDF vector, PNG300dpi and source CSV.\n\n"+"\n".join(captions), encoding="utf-8")
    diagnosis_report(manifest, main_runs, fixed, calibration, horizon, pairs, fleet_table, reasons_table, gate_table)
    save_json(OUT/"verification.json", dict(status="diagnostic_complete_not_paper_ready", audited_records=len(frame),
        oracle_complete=int(oracle.complete_service.sum()), online_runs=len(frame)-len(oracle),
        root_coverage_min=main_runs[main_runs.algorithm != "Greedy"].root_action_coverage.min(),
        full_campaign_started=False, figures=list(figure_links), source_sha256=manifest["source_sha256"]))
    print(f"Audited {len(frame)} records; wrote {len(figure_links)} meaningful diagnostic figures and Markdown report.")


def representative_figures(raw, save):
    instance = load_instance(BENCHMARK/(raw["metadata"]["instance"]+".txt"))
    geometry = []
    for node in (instance.infrastructure.depot,)+instance.infrastructure.stations+instance.customers:
        geometry.append(dict(kind="node", node=node.id, node_kind=node.kind, x=node.x, y=node.y,
                             x_end=np.nan, y_end=np.nan, vehicle=np.nan))
    for step in raw["steps"]:
        if step["distance"]:
            a,b=step["before"]["location"],step["after"]["location"]
            geometry.append(dict(kind="arc", node="", node_kind="", x=a["x"],y=a["y"],x_end=b["x"],y_end=b["y"],vehicle=step["before"]["id"]))
    data = pd.DataFrame(geometry)
    fig, ax = plt.subplots(figsize=(8,6))
    for row in data[data.kind == "arc"].itertuples():
        ax.plot([row.x,row.x_end],[row.y,row.y_end],color=".55",alpha=.2,linewidth=.8,zorder=1)
    for kind,marker,color,label in [("c","o","#326eae","Customers"),("f","^","#21855b","Stations"),("d","s","#b53d40","Depot")]:
        nodes=data[(data.kind=="node") & (data.node_kind==kind)]
        ax.scatter(nodes.x,nodes.y,marker=marker,c=color,s=28 if kind=="c" else 65,label=label,zorder=3)
    ax.set(xlabel="x",ylabel="y",aspect="equal",title=f"c101_21: 100 served, {raw['metrics']['vehicles_activated']} activated EVs")
    ax.legend()
    save("representative","representative_routes",fig,data,
         "Pre-specified c101_21 coordinated run, DoD=.5, seeds0 (n=1 trajectory). All activated route arcs are shown in gray to avoid a large indistinguishable color legend; depot/stations/customers are distinct. Complete service is required for this figure, but the vehicle count is disclosed and no optimality claim is made. No error bars or distance comparison. Concurrent diagnostic planning.")
    releases=dict(raw["scenario"]["customer_release_times"])
    rows=[]
    for c in instance.customers:
        step=next((s for s in raw["steps"] if s["served"]==c.id),None)
        rows.append(dict(record_type="customer",customer=c.id,release=releases[c.id],dispatch=step["before"]["time"] if step else np.nan,
                         service=step["service_start"] if step else np.nan,vehicle=step["before"]["id"] if step else np.nan))
    timeline=pd.DataFrame(rows).sort_values(["release","customer"])
    # Show one route chosen by longest served sequence, then smallest ID, not by quality.
    counts=Counter(s["before"]["id"] for s in raw["steps"] if s["served"])
    vehicle=min(counts,key=lambda k:(-counts[k],k))
    soc=[]
    for n,s in enumerate(raw["steps"]):
        if s["before"]["id"]!=vehicle: continue
        arrival=s["before"]["battery"]-s["distance"]*instance.infrastructure.parameters.consumption
        for phase,time,battery in [("departure",s["before"]["time"],s["before"]["battery"]),("arrival",s["arrival"],arrival),("finish",s["after"]["time"],s["after"]["battery"])]:
            soc.append(dict(record_type="soc",vehicle=vehicle,step=n,phase=phase,time=time,battery=battery,action=s["action"]["kind"]))
    soc=pd.DataFrame(soc)
    fig,axes=plt.subplots(2,1,figsize=(10,8),gridspec_kw={"height_ratios":[2,1]})
    for field,marker,label in [("release","|","Release"),("dispatch","x","Assignment"),("service",".","Service start")]:
        axes[0].scatter(timeline[field],np.arange(len(timeline)),marker=marker,s=18,label=label)
    axes[0].set(ylabel="Customer (release-sorted index)",title="Disclosure, assignment and service: all 100 requests")
    axes[0].legend(ncol=3)
    ordered=soc.sort_values(["step","time"],kind="stable")
    axes[1].plot(ordered.time,ordered.battery,color=COLORS["Coordinated"])
    charges=ordered[(ordered.action=="charge") & (ordered.phase=="finish")]
    axes[1].scatter(charges.time,charges.battery,marker="^",color="#b53d40",label="Charge completion")
    axes[1].set(xlabel="Simulation time",ylabel="Battery energy",title=f"EV{vehicle}: route with most served customers (lowest-ID tie break)")
    if not charges.empty: axes[1].legend()
    save("representative","representative_evolution",fig,pd.concat([timeline,soc],ignore_index=True),
         f"Same pre-specified n=1 c101_21 run. Top: all100 release, assignment and service times, ordered by release then ID. Bottom: EV{vehicle}, chosen by maximum served count with smallest-ID tie break, with exact travel/charging SOC points. Other EVs are not hidden from the route/source records. No uncertainty bars, distance comparison or population inference. Concurrent planning; horizontal axes are physical simulation time.")


def diagnosis_report(manifest, main, fixed, calibration, horizon, pairs, fleet, reasons, gate):
    old = pd.read_csv("results/paper_v1_fixed_fleet/B/summaries/per_run.csv")
    instances=set(main.instance)
    old=old[old.instance.isin(instances) & old.DoD_target.isin([0,.5]) & (old.scenario_seed==0) & (old.algorithm_seed==0) & old.algorithm.isin(LABELS)]
    old["Algorithm"]=old.algorithm.map(LABELS)
    v1=old.groupby(["Algorithm","DoD_target"]).agg(Service_pct=("service_ratio",lambda x:100*x.mean()),Runs=("instance","count")).reset_index()
    metrics=["mean_visible_customers","mean_raw_feasible_customers","mean_shortlisted_customers","fraction_feasible_pruned",
             "root_action_coverage","premature_returns","long_waits_with_feasible_work","wait_selections","return_selections",
             "finished_while_known_customers_remain","customers_losing_sampled_feasibility"]
    counter=main.groupby(["algorithm","DoD"])[metrics].mean().reset_index()
    selected=manifest["selection"]["budget"]
    static=main[(main.algorithm=="Coordinated") & (main.DoD==0)]
    dynamic=main[(main.algorithm=="Coordinated") & (main.DoD==.5)]
    h=horizon.groupby("horizon").agg(service=("service_ratio","mean"),EVs=("vehicles_activated","mean"),planning_s=("total_planning_time","mean")).reset_index()
    idle = pd.read_csv(OUT/"tables/csv/idle_spells.csv")
    idle = idle[idle.Algorithm == "COORDINATED_MPC_MCTS"]
    lines=["# Incomplete-Service Diagnosis", "", "## Status and Oracle",gate,
        "All12 offline reference replays serve100/100 and return safely. Reference and scenario generation were not changed. Oracle routes are never policy inputs or online comparison rows.",
        "## V1 Evidence", markdown(v1),
        "V1 all704 runs had incomplete service, including DoD0. A passing physical audit establishes legality, not global routing quality. Original source commit51a2559 and byte-verified paper_v1_fixed_fleet archive preserve that evidence.",
        "## Fleet Treatment",fleet,
        "The hard cap is a restrictive modeling assumption, but improved flexible service must be read alongside the larger activated fleet. V1/V2 changes are not individually randomized causal ablations. The V2 fixed control shares root-coverage/budget/wait settings, but the flexible mechanism also changes depot proposal sharing and busy-intent coverage.",
        "## Root Exploration", f"Selected common nominal budget: {selected}. Candidates are bounded before search. Every admissible root action receives a rollout before UCT revisits; actual simulations are max(nominal, root action count). Coverage of the pruned root set is not coverage of all physically feasible customers. Calibration details: [budget table](../results/paper_v2/tables/markdown/ablations.md).",
        "## Visible Set, Pruning and Wait/Return",markdown(counter),
        "## Cumulative WAIT Failure",markdown(idle),
        "The per-action long-WAIT counter is zero because individual waits are bounded at10. This does NOT mean active idling is fixed: the physical trace audit above concatenates consecutive waits and exposes long spells while direct feasible work existed at their start. In static c201_21, 23,943 WAIT selections include140 long feasible-work spells; maximum cumulative idle is3150 simulation units. The run spent6097.92s planning. This is an unresolved algorithmic defect, not a successful performance result.",
        "Counters are per-run means followed by equal-instance averaging, not pooled customer-independent observations. Root coverage is not applicable to Greedy. Raw feasibility tests direct authoritative next-service actions for ready EVs plus one reserve template; it excludes exhaustive charging repairs. Last feasible times and cause categories are sampled diagnostic evidence only.",
        f"Coordinated mean static service: {100*static.service_ratio.mean():.2f}%; dynamic: {100*dynamic.service_ratio.mean():.2f}%. Compare paired rows rather than interpreting this two-level development sample as a general dynamicity effect.",
        "The visible-set and pruning counters test the proposed branching explanation, but do not prove pruning was the unique V1 cause. No nearest-only ranking or full-candidate counterfactual was silently substituted. Full root coverage removes one identified exploration defect; finite-horizon coverage and overlapping predicted tails remain optimistic.",
        "## Algorithm Weakness Found During Development",
        "A naive lazy reserve attained100/100 on the first c101_21 controls by activating100 vehicles. This was rejected as a satisfactory routing result. Adding busy predicted tails to coordinated union coverage reduced redundant immediate departures but exposed repeated WAIT replanning. The final method wakes idle EVs on new releases or bounded-wait expiry, returns when no known request passes cheap capacity/time checks, and excludes station-cycle-invalid fallbacks from rollout choices. Development probes, including failures, are not pooled with the final diagnostic matrix.",
        "## Coordination and Horizon",markdown(pairs),markdown(h),
        "No significance claim. Coordination differences include the explicit treatment of busy predicted tails; independent control remains local. Hp1 uses the same coordinated fleet manager as Hp3/5 so this is a horizon-only diagnostic, not a separate independently designed baseline.",
        "## Every Final Unserved Customer", reasons,
        "[Complete per-customer diagnostic table](../results/paper_v2/all_diagnostic_unserved_customers.csv). SEARCH_NEVER_SELECTED denotes a witnessed direct feasible opportunity not converted into service; TIME_WINDOW_EXPIRED is a final condition, not proof that expiry was unavoidable. Charging reachability cannot be certified by a direct-action failure alone.",
        "## Scientific Decision",
        "The full campaign remains blocked regardless of test success. Review static service, extra fleet, waiting and runtime together. Complete service alone, especially using many extra routes, does not demonstrate a strong fleet/distance solver. Remaining work is to validate economical route integration and reserve admission without optimistic-tail deferral, and then repeat a bounded diagnostic comparison before authorizing final breadth.",
        "## Proposed Configuration",f"No final configuration is accepted. The recorded quality-only rule selected{selected}, but runtime and fleet inflation fail the gate. Keep homogeneous lazy reserve K_max=n, charged root coverage and the exact physical model; use32 as a lower-cost development control when testing future corrections to route integration, overlapping forecasts and repeated idling. Hp5/L3/partial and limits12/4/5 remain diagnostic settings, not a validated final recommendation. Do not rerun the full grid.",
        "## Presentation Scope", "Only measured diagnostics receive figures. No one-point DoD plots, no complete-service distance plot for empty strata, no empty Top-L/charging/realtime figures. Main report: [PAPER_RESULTS.md](../results/paper_v2/PAPER_RESULTS.md).", ""]
    Path("docs/incomplete_service_diagnosis.md").write_text("\n\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

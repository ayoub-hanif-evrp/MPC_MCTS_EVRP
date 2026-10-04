"""Publish frozen follow-up diagnostics without rewriting the V2 campaign."""

from hashlib import sha256

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from evrp.audit import audit_record
from evrp.storage import ROOT, load_json, save_json
from scripts.report_v2 import markdown

OUT = ROOT / "results/development_route_continuity"
METHODS = {"GREEDY": "Greedy", "INDEPENDENT_MPC_MCTS": "Independent", "COORDINATED_MPC_MCTS": "Coordinated"}


def main():
    rows, losses, index = [], [], []
    for manifest_path in sorted(OUT.rglob("controls_manifest.json")):
        manifest = load_json(manifest_path)
        if manifest["status"] != "completed" or len(manifest["records"]) != 36:
            raise RuntimeError("Incomplete controls cannot be published as complete")
        for entry in manifest["records"]:
            path = ROOT / entry["path"]
            record = load_json(path)
            errors = audit_record(record)
            if errors:
                raise RuntimeError((path, errors))
            variant = "Continuity + insertion" if record["effective_config"].get("route_insertion") else "Continuity only"
            m, meta = record["metrics"], record["metadata"]
            searches = [s for s in record["searches"] if s["root_action_count"]]
            row = dict(Variant=variant, Instance=meta["instance"], Algorithm=METHODS[meta["algorithm"]],
                       DoD=meta["DoD_target"], Served=m["customers_served"], EVs=m["vehicles_activated"],
                       K_ref=meta["K_ref"], Distance=m["total_distance"], Planning_s=m["total_planning_time"],
                       Waits=m["wait_selected"], Insertions=m.get("route_insertions", 0),
                       Root_coverage=min((s["fraction_root_actions_evaluated"] for s in searches), default=np.nan),
                       Max_branching=max((s["root_action_count"] for s in searches), default=0),
                       Actual_simulations=m["mcts_iterations"], Source=manifest["source_sha256"])
            rows.append(row)
            losses.extend({"Variant": variant, "Algorithm": row["Algorithm"], **loss}
                          for loss in record["diagnostics"]["unserved"])
            index.append(dict(path=entry["path"], sha256=sha256(path.read_bytes()).hexdigest(), source=manifest["source_sha256"]))
    frame = pd.DataFrame(rows)
    if len(frame) != 72:
        raise RuntimeError("Expected two completed 36-condition development variants")
    table_dir = OUT / "tables"
    table_dir.mkdir(exist_ok=True)

    def export(name, table):
        table.to_csv(table_dir / f"{name}.csv", index=False)
        (table_dir / f"{name}.md").write_text(markdown(table) + "\n", encoding="utf-8")
        (table_dir / f"{name}.tex").write_text(table.to_latex(index=False, escape=True, float_format="%.3f"), encoding="utf-8")
        return markdown(table)

    export("all_controls", frame)
    export("unserved_customers", pd.DataFrame(losses))
    pd.DataFrame(index).to_csv(OUT / "raw_index.csv", index=False)
    means = frame.groupby(["Variant", "Algorithm", "DoD"], sort=False)[["Served", "EVs", "Planning_s", "Waits"]].mean().reset_index()
    summary = export("method_summary", means)
    proposed = frame[frame.Variant == "Continuity + insertion"]
    coordinated = proposed[proposed.Algorithm == "Coordinated"]
    compact = coordinated.pivot(index="Instance", columns="DoD", values=["Served", "EVs", "Planning_s"])
    compact.columns = [f"{metric}_{'static' if dod == 0 else 'dynamic'}" for metric, dod in compact.columns]
    compact = compact.reset_index()
    compact["K_ref"] = compact.Instance.map(coordinated.drop_duplicates("Instance").set_index("Instance").K_ref)
    main_table = export("coordinated_by_instance", compact)
    pairs = []
    for _, c in coordinated.iterrows():
        other = proposed[(proposed.Instance == c.Instance) & (proposed.DoD == c.DoD) & (proposed.Algorithm == "Independent")].iloc[0]
        equal_service, equal_fleet = c.Served == other.Served, c.EVs == other.EVs
        pairs.append(dict(Instance=c.Instance, DoD=c.DoD, Delta_unserved=other.Served-c.Served,
                          Delta_EVs=c.EVs-other.EVs if equal_service else np.nan,
                          Delta_distance=c.Distance-other.Distance if equal_service and equal_fleet else np.nan))
    export("paired_methods", pd.DataFrame(pairs))
    figure_dir = OUT / "figures"
    figure_dir.mkdir(exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(13, 7), layout="constrained")
    instances = sorted(proposed.Instance.unique())
    colors = ["#777777", "#008b83", "#c94b52"]
    for column, dod in enumerate((0., .5)):
        for method_index, method in enumerate(METHODS.values()):
            data = proposed[(proposed.DoD == dod) & (proposed.Algorithm == method)].set_index("Instance").loc[instances]
            x = np.arange(len(instances)) + (method_index-1)*.25
            axes[0, column].bar(x, data.Served, width=.24, color=colors[method_index], label=method)
            axes[1, column].bar(x, data.EVs, width=.24, color=colors[method_index])
        axes[0, column].set(title=f"{'Static' if dod == 0 else 'Dynamic'} (DoD={dod:g})", ylabel="Served / 100", ylim=(0, 107))
        axes[1, column].set(ylabel="Activated EVs", ylim=(0, 70))
        for ax in axes[:, column]:
            ax.set_xticks(np.arange(len(instances)), [name.split("_")[0].upper() for name in instances])
            ax.spines[["top", "right"]].set_visible(False)
        axes[0, column].legend(loc="lower left", ncol=3, fontsize=9)
    fig.suptitle("Executable route continuity + insertion: six-case development controls", fontsize=14)
    stem = figure_dir / "service_and_fleet"
    fig.savefig(stem.with_suffix(".png"), dpi=300)
    fig.savefig(stem.with_suffix(".pdf"))
    plt.close(fig)
    proposed.to_csv(figure_dir / "service_and_fleet_data.csv", index=False)
    caption = ("Service and fleet by instance for continuity plus insertion. 36 runs: six instances, two DoD levels, "
               "three algorithms; one seed pair (0,0) per bar, no aggregation or error bars. Fleet must be read with service; "
               "low fleet with missed customers is not superior. Distance is not plotted. Sequential development executions, "
               "not isolated realtime benchmarks. Exact data: figures/service_and_fleet_data.csv.\n")
    (OUT / "FIGURE_CAPTIONS.md").write_text("# Follow-Up Figure\n\n" + caption, encoding="utf-8")
    report = ["# Route-Continuity Follow-Up: Development Only",
              "**Full paper campaign remains blocked.** Both variants are opt-in, not approved replacements for the paper method.",
              "## Scope", "72 unique online controls (36 per variant), six100-customer instances, DoD0/.5, seeds0/0. "
              "Four probes per variant reuse grid records and are not additional observations. Hp5/L3, partial charging, "
              "limits12/4/5,32 nominal simulations with charged root coverage, lazy reserve K_max=100. All methods share "
              "the variant's fleet manager; Greedy has a one-service local horizon. Sequential development timing, one BLAS thread.",
              "## Method Change", "Retained feasible suffixes and exclusive ownership replace optimistic unbound tails. "
              "Optional due-date-ordered insertion integrates known requests after immutable busy actions. No hidden requests "
              "or future releases enter planning. This is a methodological change requiring review, not an equivalent optimization. "
              "[Protocol](../../docs/route_continuity_followup.md).",
              "## Coordinated Results", main_table,
              "All six static cases serve100/100. Dynamic rc101_21 still serves98/100. Coordinated has zero selected WAITs "
              "in all12 controls of either variant. Insertion lowers dynamic EV use substantially but does not repair all service losses.",
              "## Method and Ablation Summary", summary,
              "Means weight six heterogeneous instances equally; these are not seeded replications. No significance claims. "
              "Insertion regresses Independent on dynamic rc101_21 from99 to97 served, and Greedy from100 to97. "
              "Lower fleet use is not universal lexicographic improvement. [Paired results](tables/paired_methods.md) "
              "report EV differences only at equal service, distance differences only at equal service AND equal fleet.",
              "## Figure", "![Service and fleet](figures/service_and_fleet.png)", caption,
              "## Losses and Limitations", "[Every unserved customer](tables/unserved_customers.md) is retained for both variants. "
              "Coordinated insertion misses C32 and C76 on dynamic rc101_21. Obligations restrict reallocations, and finite horizon, "
              "pruning and Top-L can still omit urgent alternatives. Diagnostic labels are not causal proofs. "
              "Static service improves and repeated idling is absent here, but dynamic service and fleet efficiency remain unresolved. "
              "Coordinated mean service is static100%, dynamic99.67%; dynamic fleet use can still be lower. "
              "32 simulations is a development budget, not a validated final recommendation. "
              "No full-charging, Top-L, realtime, robustness or full56-instance campaign was launched.",
              "## Verification", "All72 records passed physical replay, release safety, unique service and safe-return audits. "
              "Every promised customer is checked against actual future service by its owner. MCTS covers every admissible root "
              "action, not every customer excluded by reservations or pruning. See [raw checksums](raw_index.csv), "
              "[all controls](tables/all_controls.md) and [test evidence](test_verification.json). "
              "V1 and original78-record V2 diagnostics remain separate. Old concurrent96-simulation timings are not a matched "
              "speedup baseline. Source snapshots and hashes preserve both development revisions.", ""]
    (OUT / "README.md").write_text("\n\n".join(report).rstrip() + "\n", encoding="utf-8")
    save_json(OUT / "verification.json", dict(audited_records=len(frame), full_campaign_started=False,
              scientific_gate="not_approved", coordinated_insertion_complete=int((coordinated.Served == 100).sum()),
              root_coverage_min=float(frame.Root_coverage.min()), sources=sorted(frame.Source.unique())))
    print(f"Published {len(frame)} audited controls; no experiments executed.")


if __name__ == "__main__":
    main()

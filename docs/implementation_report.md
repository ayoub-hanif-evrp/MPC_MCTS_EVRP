# Implementation Report (2026-10-03)

Historical implementation snapshot, not current experiment status. V1 later
completed704 conditions with incomplete service throughout. V2 diagnostics and
their failed scientific/runtime gate are documented in
[the current report](../results/paper_v2/PAPER_RESULTS.md) and
[incomplete-service diagnosis](incomplete_service_diagnosis.md).

## Outcome and Scope

The requested service-first objective correction and research-output pipeline are
implemented in the existing architecture. No automatic commit or push was made.
No full main benchmark, ablation grid, or realtime grid was run. Original Schneider
benchmark files have no working-tree changes; no external dataset was downloaded.

Latest full test command: `python -m pytest -q`: **116 passed in 9.33 seconds**.
All 24 current small-case records pass independent structural/physical/information
audits. There are zero execution failures, six complete-service runs and eighteen
incomplete-service runs across four algorithms. Incompleteness is reported, not
discarded or misclassified as a physical violation.

## Changed Files

- `evrp/mpc.py`, `mcts.py`: service-first proposal keys, bounded UCT reward,
  explicit proposal coverage, activation, distance decomposition and root metadata.
- `evrp/coordinator.py`: three sequential SciPy binary MILPs for coverage,
  new activations, then distance; no production enumeration or large penalty.
- `evrp/reference.py`, `scenario.py`: Pareto charging repair, small subset search,
  route elimination, dependency versions and stale-artifact rejection.
- `evrp/simulator.py`: candidate/selection records, coverage and activation metrics.
- `evrp/experiments.py`: shared persisted scenarios, provenance-bound IDs, structured
  result sections, safe resume, failure retention and stronger runtime trace checks.
- `evrp/versions.py`, `validation.py`, `audit.py`: version constants, published
  reference gate, disk-level schema/hash/trace/configuration integrity auditing.
- `evrp/analysis.py`, `plotting.py`, `cli.py`: hierarchical service-first statistics,
  conditional pairing, CSV/LaTeX tables, exact-data figures and study commands.
- `configs/validation.yaml`, `pilot.yaml`, `main.yaml`, `representative.yaml` added;
  debug/default/benchmark/ablations/realtime configurations updated.
- `tests/test_hierarchy.py`, `test_reporting.py`, `tests/__init__.py` added;
  planning/regression objective expectations updated.
- README, methodology, assumptions, this report, results policy and `.gitignore`
  updated; generated summaries/tables/figures and current references/scenarios added.
- Existing result directories moved intact to `results/archive_preobjective_fix/`.
  Earlier reporting-pipeline trials remain under an excluded raw pilot subarchive.

## Exact Formulation

Final execution minimizes `(unserved customers, activated EVs, distance)`
lexicographically. Local MPC minimizes `(-predicted services, D + terminal_return,
charging time, waiting time, completion time, canonical actions)`.

MCTS reward is `R = N - 0.5*D_total/B`, where
`B = speed*(depot_due-current_time)` and the ratio is zero when B=0. Feasibility
bounds the ratio in [0,1], so another service improves reward by at least 0.5.
Explicit lexicographic keys, not mean UCT rewards, retain root trajectories/top-L.

The coordinator has binary proposal variables y and union-coverage variables z.
Exactly one proposal is chosen per ready EV; each first-action customer has at most
one commitment. `z_i <= sum(covering y)` and `y_kp <= z_i` for every covered i
define unique intent coverage. Stage 1 maximizes sum z and fixes it; stage 2
minimizes new first-action activations and fixes them; stage 3 minimizes sum D*y.
Hidden/committed intent customers are rejected, tails may overlap, and only first
actions execute. See [methodology](methodology.md) for equations and scope.

## Published Reference Checks

All requested validation cases pass, including exact published vehicle counts:

| Instance | Published / our EVs | Published distance | Our distance |
| --- | --- | ---: | ---: |
| c101C5 | 2 / 2 | 257.75 | 257.7474518642 |
| c103C5 | 1 / 1 | 176.05 | 176.0544331488 |
| c206C5 | 1 / 1 | 242.56 | 242.5556517150 |
| c208C5 | 1 / 1 | 158.48 | 158.4806595843 |

Source: Schneider et al., Technical Report 02/2012, Table 3, CPLEX column;
[citation and rounding note](methodology.md#reference-validation-and-dynamicization).
The configured tolerance is 0.011 distance units. This validation says nothing
about optimality of larger heuristic references. Current reference/scenario
versions are saved in every dependent artifact; old versions fail explicitly.

## Coordinated Smoke Results

All rows use COORDINATED_MPC_MCTS, H_p=3, L=3, 64 iterations per replan,
scenario seed 0 and algorithm seed 0. Timing is summed measured planning wall time.
Distances on incomplete rows are raw diagnostics, NOT superior routing outcomes.

| Instance | Target / realized DoD | Served | EVs | Distance | Planning seconds |
| --- | --- | ---: | ---: | ---: | ---: |
| c101C5 | 0.00 / 0.00 | 5/5 | 2 | 283.32 | 0.463 |
| c101C5 | 0.50 / 0.60 | 4/5 | 2 | 198.34 | 0.293 |
| r104C5 | 0.50 / 0.20 | 5/5 | 2 | 136.69 | 0.309 |
| rc105C5 | 0.50 / 0.60 | 4/5 | 2 | 168.05 | 0.341 |
| c101C10 | 0.50 / 0.50 | 9/10 | 3 | 489.83 | 1.577 |
| c103C15 | 0.50 / 0.40 | 13/15 | 3 | 570.84 | 2.840 |

Every EV returned safely; battery, load, windows, unique service and information
boundaries passed replay. All-Wait no longer dominates service. In the fixed
representative's first epoch, the coordinator selects service to C64 for one EV
and leaves the other idle, avoiding a duplicate activation for the same coverage.
Unit tests also verify an already-active EV covering work while an unused EV waits.

Greedy, H1 and independent MPC-MCTS were run on precisely these same six scenarios,
not on additional main instances. Their full outcomes appear in `per_run.csv`.
Different algorithms win different pilot service outcomes: for example Greedy
serves 14/15 on c103C15 versus coordinated 13/15. This is not evidence of superiority
of either method from one seed. Distances are compared only under the stated filters.

## Results Layout and Artifacts

```text
results/
  archive_preobjective_fix/
  raw/{validation,pilot,main,ablations,realtime}/
  traces/representative/
  summaries/
  tables/{csv,latex}/
  figures/{main,ablations,diagnostics,representative}/
```

Summaries include per_run, main_by_family, main_overall, paired_comparisons,
computation, failures, reference_validation, seven ablation tables, and audit CSV/MD.
Thirteen CSV/LaTeX table pairs were exported (six core plus seven ablation layouts).
The seven ablation tables are empty because those experiments were not run.

Fourteen figure triplets (PDF, 300-dpi PNG, exact-data CSV) were generated:

- Main: service/full-service versus DoD, vehicles versus DoD, complete-only distance,
  and coordinated-versus-independent paired differences.
- Diagnostics: mean/p95 latency versus size, separately for DoD 0 and 0.5.
- Ablations: horizon, budget, L and charging export layouts, explicitly marked
  "not run" with no observations. These are not scientific findings.
- Fixed representative: routes, release/assignment/service timeline, SOC with
  charging markers, and MPC first-action/release timeline.

The representative proposal table is also exported as CSV/LaTeX. Route labels,
SOC, unserved-customer visibility, timelines, and conditional-distance plots were
visually inspected. Overlapping depot/S0 labels were corrected. The representative
case was fixed before inspection and remains incomplete; C100 is visibly unserved.

All 61 archived pre-fix files were verified against their committed Git contents.
The final `git diff --check` passes, and the original benchmark has no changes.
Table exports were tested through a CSV round trip, including empty ablation
outcome columns and the actual maximum observed planning latency.

## Remaining Methodological Limits

The structural development gates pass; solution quality is not validated for the
full paper study. Four of six coordinated smoke runs remain incomplete. Intent
coverage is optimistic, and locally retained top-L charge alternatives can target
the same customer, omitting other observed customers from coordinator choices.
The representative first epoch demonstrates this limited proposal diversity.
Increasing L or search budget is an ablation question, not a silent outcome-tuned fix.

Finite service horizons, discrete charge targets, deterministic myopic information,
and larger-reference heuristic quality remain limitations. No future-demand model
or full-service guarantee has been added. Scenario repeats within an instance may
be correlated; CIs are descriptive. Pilot DoD groups contain different instance
mixes, so their plotted slopes are not controlled dynamicity effects. Latency
depends on this machine; average run-p95 is not a pooled percentile.

## Reproduction and Next Commands

```powershell
python -m pytest -q
python -m evrp.cli validate --config configs/validation.yaml
python -m evrp.cli smoke --config configs/pilot.yaml
python -m evrp.cli smoke --config configs/pilot.yaml --algorithm GREEDY
python -m evrp.cli smoke --config configs/pilot.yaml --algorithm MPC_MCTS_H1
python -m evrp.cli smoke --config configs/pilot.yaml --algorithm INDEPENDENT_MPC_MCTS
python -m evrp.cli aggregate
python -m evrp.cli audit
python -m evrp.cli tables
python -m evrp.cli plot --study pilot
python -m evrp.cli representative
```

For a deliberately expanded pilot use `python -m evrp.cli benchmark --config
configs/pilot.yaml`. After reviewing the methodological limits and explicitly
deciding to proceed, the unexecuted main command is `python -m evrp.cli benchmark
--config configs/main.yaml`; ablations use `python -m evrp.cli ablations --config
configs/ablations.yaml`; realtime uses `python -m evrp.cli realtime --config
configs/realtime.yaml`. Main is never launched by default.

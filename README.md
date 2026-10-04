# Event-Triggered Coordinated Multi-Agent MPC for D-EVRPTW-PR

Python 3.11+ research implementation using only the local Schneider E-VRPTW
benchmark. Each EV has an explicit MPC controller; MCTS approximately solves its
deterministic finite-horizon problem. An intent-aware coordinator selects compatible
first actions. By default, predicted tails are intentions, never reservations.
An experimental opt-in variant retains executable route reservations instead;
it is a methodological change requiring review.

**Status:** V1 completed all 704 conditions, but every run had incomplete service.
It is preserved as [V1 diagnostic evidence](results/paper_v1_fixed_fleet/ARCHIVE_NOTICE.md),
not final paper results. V2 completed only the bounded six-instance diagnostics:
12 offline oracle controls and 66 online conditions. The oracle serves every
customer; the online method still has fleet-efficiency, service and runtime
weaknesses. The full paper executor is blocked pending scientific review.

The [latest follow-up](results/development_route_continuity/README.md) adds two
36-condition development grids with retained routes and optional active-route
insertion. Static service and repeated idling improve, but dynamic losses and
fleet-efficiency limitations remain. Both changes are opt-in; no new full
campaign has been launched. See the [protocol](docs/route_continuity_followup.md).

Read the [V2 master report](results/paper_v2/PAPER_RESULTS.md),
[per-instance appendix](results/paper_v2/PER_INSTANCE_RESULTS.md), and
[incomplete-service diagnosis](docs/incomplete_service_diagnosis.md).

## Objective and Architecture

```text
EVAgent -> MPCController -> MPCPlanningProblem -> MCTSOptimizer
        -> top-L proposals -> sequential-MILP Coordinator
        -> execute FIRST action -> event-driven observation -> replan

Final fleet objective: lexicographically minimize
    (customers unserved, activated vehicles, total travel distance).

Local proposal ordering:
    (-predicted services, predicted distance + safe return distance,
     charging time, waiting time, completion time, canonical actions).

UCT reward: services - 0.5 * total_predicted_distance / distance_bound
    distance_bound = speed * (depot_due - current_time).
```

Feasible return bounds normalized distance in [0,1], so one additional service
always dominates the distance term. Explicit lexicographic keys still select the
best trajectory per first action and top-L. MCTS is an approximate numerical
optimizer, not the controller or a stochastic future-request predictor.

The coordinator solves three successive binary MILPs: maximize unique observed
customer coverage in selected intentions; fix that optimum and minimize new
first-action activations; fix both optima and minimize summed predicted distances.
There is one proposal per ready EV and at most one immediate commitment per customer.
Tail overlap is allowed. Busy EVs are not interrupted. Unused EVs may wait without
activation. Local progress and intent coverage do not guarantee global full service.

## Data and Model

All 92 files under `data/evrptw_instances/` are immutable. No other dataset is used.
The parser reads `StringID Type x y demand ReadyTime DueDate ServiceTime` and
`Q C r g v`. Missing parameters are errors. Euclidean distance is unrounded;
travel time is `distance/v`, consumption is `r*distance`, and charging time is
`g*charged_energy`. Windows constrain service start. Every accepted action must
preserve battery, freight, time-window, and safe-depot-return feasibility.

One tour per EV, homogeneous fleet, uniform station hours/rate, unlimited
simultaneous chargers, no reloads, queues, stochastic travel, or future information.
Serve and recharge are non-preemptive travel-plus-service macro-actions. Passive
Wait is interruptible. All co-timed releases/completions precede planning.

The original dataset is never written. Generated artifacts are in separate folders.
V1 fixed fleet size K to the static reference. V2 diagnostics instead use an
exchangeable lazy reserve with K_max equal to the customer count; K_ref is a
benchmark, not a hard online cap. No new full campaign is authorized.
For five-customer
instances, subset/permutation route search uses Pareto full-charge repair; larger
instances use deterministic multistart insertion, targeted route elimination,
and relocate. Larger-instance references remain heuristics.

Four external validation checks match Table 3 of Schneider's technical report:
`c101C5: 2 / 257.75`, `c103C5: 1 / 176.05`, `c206C5: 1 / 242.56`,
`c208C5: 1 / 158.48` (vehicles / rounded distance). These are validation metadata,
not another benchmark. Details and citation are in [methodology](docs/methodology.md).

## Scenarios and Fair Comparisons

Dynamicization is **reference-schedule-preserving, inspired by Yang et al.**:
`upper_i = min(ReadyTime_i, reference_predecessor_departure_i)`. Selected eligible
requests receive seeded uniform releases in `(0, upper_i]`; others are initially
known. Exact-count selection uses half-up rounding and saturates at eligibility;
Bernoulli selection is also supported. Target and realized DoD are both recorded.
Uniform sampling is our assumption, not a claim about Yang's original distribution.

Scenario files are generated once and reused across online algorithms. Their base
SHA, reference hash, reference solver, scenario generator, and objective versions
are checked. Stale files fail explicitly; new dependencies produce new paths.
Policies never receive hidden customers, the future calendar, or reference routes.

Online algorithms: `GREEDY`, `MPC_MCTS_H1`, `INDEPENDENT_MPC_MCTS`,
`COORDINATED_MPC_MCTS`. `STATIC_REFERENCE` is offline validation only and is
rejected from the main online grid. Scenario and algorithm seeds are independent.

## Commands

From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m evrp.cli validate --config configs/validation.yaml
python -m evrp.cli scenario --instance c101C5 --config configs/pilot.yaml
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

`smoke` runs exactly six small cases: c101C5 at DoD 0/.5, r104C5, rc105C5,
c101C10 and c103C15 at .5. It never runs a 100-customer instance. The default CLI
uses the pilot config. `--dynamicity`, `--scenario-seed`, and `--scenario` are
available for individual runs; explicit scenario settings must match the config.

Individual larger studies can also be executed explicitly:

```powershell
python -m evrp.cli benchmark --config configs/pilot.yaml
python -m evrp.cli benchmark --config configs/main.yaml
python -m evrp.cli ablations --config configs/ablations.yaml
python -m evrp.cli realtime --config configs/realtime.yaml
python -m evrp.cli aggregate
python -m evrp.cli plot --study main
```

Main performs the reference-validation gate first. Passing small checks does not
establish large-instance solution quality or justify a performance claim.

## Results and Statistics

Separate validation/pilot/main/ablations/realtime directories prevent study mixing.
Run IDs hash configuration, scenario/base hashes, objective version, git commit,
and actual source content. Runtime records include machine, packages, UTC timestamp,
effective-config hash, physical traces, proposals, search statistics, and failures.
Different configurations never overwrite each other. Fixed-iteration seeded logical
behavior is reproducible; measured latency and wall-clock searches are not bitwise
reproducible. Parallel workers preserve logical seed/collection order.

Aggregation independently audits disk records. Structural-invalid runs are excluded
from scientific tables but retained in the failures report. Incomplete runs remain
in service statistics. Distance summaries use **complete-service runs only**.
Paired vehicles require equal service counts; paired distance also requires equal
vehicle counts. Repeated algorithm seeds are averaged within instance/scenario
before descriptive means, medians, sample SDs, and Student-t 95% CIs. No significance
is inferred; intervals for fewer than two environmental observations are undefined.

V2 exports Markdown/CSV/LaTeX tables and meaningful study-specific diagnostic
figures as PDF vector, PNG at 300 dpi and exact-data CSV. No empty figures or
one-point dynamicity curves are generated. Missing V2 charging, Top-L, robustness
and realtime studies are explicitly marked unmeasured, not filled using V1 data.
Regenerate reports without running experiments: `python -m scripts.report_v2`.
See [results policy](results/README.md) and [assumptions](docs/assumptions.md).

## Compact Paper Campaign

The former 17,017-job design is **cancelled**. Its 58 completed records remain
archived in place; do not restart `scripts.run_full_campaign` or `evrp.campaign`.
The compact design is specified by `configs/paper.yaml` and documented in
[performance analysis](docs/performance_analysis.md). Planning never starts runs:

```powershell
python -m evrp.cli estimate --config configs/paper.yaml --workers 4 --output "$env:LOCALAPPDATA\EVRP\paper"
```

That design completed as V1. Its performance-only gate is insufficient for V2.
`evrp.cli paper --execute` is now explicitly blocked pending scientific review.
The only new experiment entry point is the bounded `scripts.diagnose_v2`; its
completed records are preserved by source/configuration identity, never silently
replaced by a new revision.

Raw computation outputs stay on the local SSD outside OneDrive. Audited summaries,
publication tables, and PNG figures with exact-data CSVs are copied back to
`results/paper`. Shared conditions across studies are computed once and referenced
by a study-membership manifest. Full traces are reserved for pilots and the fixed
representative example. Paper summary traces retain replayable physical actions
and information-integrity evidence, not every rejected candidate proposal.

Outer parallelism is limited by physical cores and measured memory, with BLAS
threads fixed to one. Realtime runs execute in isolation. Concurrent throughput
timings must not be interpreted as isolated decision latency. Every launch prints
its job count, reusable count, remaining count, and estimated duration. Unknown
timings or a failed calibration gate block the paper campaign.

## References

- Schneider, Stenger, Goeke (2014), *The Electric Vehicle-Routing Problem with Time
  Windows and Recharging Stations*. [DOI](https://doi.org/10.1287/trsc.2013.0490).
- Keskin and Catay (2016), *Partial recharge strategies for the electric vehicle
  routing problem with time windows*. [DOI](https://doi.org/10.1016/j.trc.2016.01.013).
- Yang et al. (2017), *Dynamic vehicle routing with time windows in theory and
  practice*. [DOI](https://link.springer.com/article/10.1007/s11047-016-9550-9).
- Kocsis and Szepesvari (2006), *Bandit based Monte-Carlo Planning*.
  [Paper](https://aima.cs.berkeley.edu/~russell/classes/cs294/s11/readings/Kocsis%2BSzepesvari%3A2006.pdf).

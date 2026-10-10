# Experiment Protocol

Status: implementation and screening. These are intended studies, not assertions
that they have run. Freeze configurations and seeds before inspecting outcomes.
Do not enlarge fleets/budgets, remove difficult cases, select favorable seeds, or
change objectives to favor a method.

## Common Configuration

```yaml
fleet_mode: fixed_reference
prediction_horizon: 5
control_horizon: 1
mcts_iterations: 32
top_L: 3
candidate_limit: 12
station_candidate_limit: 4
charge_target_limit: 5
charging_mode: partial
route_continuity: true
regret_repair: true
proposal_selection: quality
dynamic_selection_mode: exact_count
parallel_agents: false
trace_level: summary
```

Share `K_ref`, physics, information boundaries, and saved scenarios across methods.
Record scenario and algorithm seeds separately. Report target and realized DoD,
mark unattainable target counts ineligible, and disclose missing conditions.

## Validation and Smoke

Run physics, information-boundary, fixed-fleet, ownership, regret-ordering, local
horizon, MILP-versus-enumeration, and seeded-execution checks. Validate references
against the repository's Schneider validation metadata. Report current pass/fail
evidence rather than repeating historical validation claims.

Smoke checks cover small C, R, and RC examples, static/dynamic releases, unique
service, safe return, and feasible retained routes before screening.

## Stage 1: Feasibility

Use exactly these six 100-customer instances:

```text
c101_21  c201_21  r101_21  r201_21  rc101_21  rc201_21
```

Use DoD `0.0/0.5`, scenario seed `0`, algorithm seed `0`, and the common
32-simulation settings. Compare `RH_REGRET`, `INDEPENDENT_MPC_MCTS`, and
`COORDINATED_MPC_MCTS`: 36 conditions. Optional GREEDY rows are sanity checks.

Preferably serve 100/100 statically on all six instances. At DoD 0.5 target mean
service at least 98%, preferably five of six complete. Show per-method and
per-instance results; pooling must not conceal a weak method or family. State
the actual pass/fail interpretation alongside its evidence.

The implemented gate was fixed before execution: coordinated static service must
be complete on all six cases, dynamic mean service must be at least 98%, and at
least five dynamic cases must be complete. All 36 conditions are recorded before
the Stage-1 decision; service failure blocks Stage 2. Technical execution/audit
failure stops immediately and cannot yield a PASS.

If static service remains poor, stop further experiments. Diagnose ownership,
insertion, pruning, horizon versus retained commitments, and candidate coverage.
Increasing MCTS budget is not the first response. Stage 2 requires an explicit
recorded Stage-1 pass; missing evidence is not a pass.

## Stage 2: Small Screening

Only after Stage 1 passes, use the same six instances at DoD `0.25/0.50/0.75`,
scenario seeds `0/1`, and algorithm seed `0`. The three required methods give
108 runs, or 144 with optional `DIVERSE_COORDINATED_MPC_MCTS`. Report ineligible,
failed, and missing conditions separately from planned grid sizes.

Write `results/screening/GATE.md` with source/configuration identity, validation
status, Stage-1 evidence, Stage-2 evidence if executed, eligibility counts, and
the decision. Primary comparisons use `customers_unserved`. Compare vehicles only
on equal-service pairs and distance only on equal-service/equal-vehicle pairs.

Report paired wins/ties/losses, mean and median differences, and a 95% paired
bootstrap CI. State sign convention, eligible pair count, resampling unit,
bootstrap seed, and replicate count; preserve pairing during resampling.

For coordinated versus each comparator, assess systematic service degradation,
meaningful dynamic service improvements or fewer EVs at equal service, breadth
across instance families, and computational practicality. Make the judgment
explicit. Unsupported direction means `GATE = FAIL` and blocks main execution.
An incomplete screen stays unevaluated and cannot be presented as PASS.

The numerical Stage-2 rule, fixed before execution, requires versus each baseline:
mean unserved difference <= 0, service losses <= wins, and at least two service or
equal-service EV improvements across at least two of C/R/RC. Every coordinated
run's p95 event-planning latency must be <= 5 seconds. Paired mean-difference CIs
use 2,000 bootstrap samples with seed 0, resampling matched scenario pairs. These
small-sample descriptive intervals do not establish independent instance-level
generalization. The thresholds and source identity are saved with the gate.

## Main Study: Explicit Execution Only

Proposed balanced instances:

```text
c101_21  c109_21  c201_21  c208_21
r101_21  r112_21  r201_21  r211_21
rc101_21 rc108_21 rc201_21 rc208_21
```

Use DoD `0.25/0.50/0.75`, scenario seeds `0/1/2`, and the three required methods.
Add diversity only if screening supports it. Keep DoD 0 as separate static sanity
evidence. Implement main but never launch it automatically: require the applicable
passing gate and explicit `main --execute`.

## Ablations and Realtime

Prioritize independent/coordinated, continuity OFF/ON, and repair OFF/ON. Secondary
comparisons use horizons `1/3/5`, top-L `1/3/5`, and quality/coverage-diverse
proposals. `MPC_MCTS_H1` is an ablation only. Avoid a factorial study, unnecessary
UCT sweeps, and unrelated charging studies.

Realtime budgets are `0.05/0.10/0.25/0.50` seconds. Deadlines take priority over
root coverage; retain a valid incumbent. Execute isolated from outer parallel
workers. Report mean/median/p95/maximum planning latency, deadline overrun rate,
service ratio, activated vehicles, and conditionally comparable distance. State
timing scope, including coordination and repair: a local MCTS budget is not an
end-to-end deadline.

## Reporting

Audit disk records before aggregation. Keep valid incomplete runs in service
statistics and disclose invalid runs/failures. Pair by instance, shared scenario,
algorithm seed, and compatible source/configuration identity. Preserve raw
precision and round on display. Never mix historical outputs into current tables
or infer superiority from studies that have not run.

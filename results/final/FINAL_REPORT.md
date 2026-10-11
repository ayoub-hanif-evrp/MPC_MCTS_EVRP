# Final MPC-MCTS EVRP Report

**Development gate: FAIL**

All outputs are development evidence until a separate holdout executes.

## Frozen Configuration

```yaml
study: final_track
fleet_mode: fixed_reference
prediction_horizon: 5
control_horizon: 1
mcts_iterations: 48
candidate_limit: 16
top_L: 5
proposal_selection: coverage_diverse
station_candidate_limit: 4
charge_target_limit: 5
charging_mode: partial
route_continuity: true
regret_repair: true
dynamic_selection_mode: exact_count
parallel_agents: false
workers: 1
trace_level: summary
diagnostics: true
max_idle_wait: 0
require_root_coverage: false
budget_mode: iterations
experiment_seed: 0
reference_solver_multistarts: 3
reference_improvement_passes: 1
reference_seed: 0
reference_label_limit: 24
instances: [c101_21, c201_21, r101_21, r201_21, rc101_21, rc201_21]
holdout_instances: [c109_21, c208_21, r112_21, r211_21, rc108_21, rc208_21]
gate:
  static_complete: 6
  dynamic_mean_service: 0.98
  dynamic_complete: 5
  max_p95_planning_seconds: 5.0
```

## Identity and Verification

- Source SHA-256: `6bea24e2211d179ba464b202f3fe4f7b1556aa5fbd85f959e3c5be9588cdc0af`.
- Config SHA-256: `b69a2d9f4ef78b80272c0dac537098729813da402baa93802a761643e113e116`.
- Git revision at run time: `432fc8b03956b90fd0de8c212996f66418893e3b`.
- Development manifest: `C:\Users\AYOUB\OneDrive - EMSI\Bureau\PHD_WORK\MPC_MCTS_Multi_agents_EVRP\results\development\attempts\6bea24e2211d_b69a2d9f\manifest.json`.
- Schneider reference validation: 4/4 passed.
- Full tests: 253 run, 0 failures, 0 errors.

## Development Results

Customers served out of 100; same K_ref within each matched scenario.

| Instance | K_ref | DoD | RH_REGRET | Independent | Coordinated |
|---|---:|---:|---:|---:|---:|
| c101_21 | 13 | 0 | 93 | 91 | 95 |
| c201_21 | 5 | 0 | 100 | 90 | 76 |
| r101_21 | 20 | 0 | 89 | 89 | 95 |
| r201_21 | 4 | 0 | 72 | 73 | 70 |
| rc101_21 | 21 | 0 | 100 | 98 | 100 |
| rc201_21 | 5 | 0 | 92 | 77 | 86 |
| c101_21 | 13 | 0.5 | 81 | 82 | 93 |
| c201_21 | 5 | 0.5 | 92 | 88 | 86 |
| r101_21 | 20 | 0.5 | 84 | 87 | 92 |
| r201_21 | 4 | 0.5 | 76 | 95 | 83 |
| rc101_21 | 21 | 0.5 | 86 | 92 | 94 |
| rc201_21 | 5 | 0.5 | 90 | 97 | 83 |

- Coordinated static complete: 1/6.
- Coordinated dynamic complete: 0/6.
- Coordinated dynamic mean service: 88.500%.
- Largest coordinated run-level p95: 7.848 s.
- Gate reason: Coordinated dynamic mean service is below 98%
- Gate reason: Coordinated dynamic service must be complete on at least five instances
- Gate reason: Coordinated static service must be complete on all six instances
- Gate reason: Coordinated run-level p95 planning time exceeds 5 seconds

## Holdout Results

Not run because the development gate did not pass.

## Development Paired Comparisons

Across the 12 matched development scenarios, coordinated-minus-baseline
unserved customers (negative is better) were:

| Baseline | Mean | Median | Coordinated wins / ties / losses |
|---|---:|---:|---:|
| Independent MPC-MCTS | +0.500 | -2 | 7 / 0 / 5 |
| RH_REGRET | +0.167 | -1 | 6 / 1 / 5 |

These are descriptive development comparisons, not holdout estimates or
significance tests. No scenario tied coordinated and independent on service,
so there is no eligible vehicle or distance comparison for that pair. Against
RH_REGRET, only static `rc101_21` tied on service; coordinated activated one
additional EV (21 versus 20), making distance comparison ineligible. Paired
holdout means, confidence intervals, and wins/ties/losses are unavailable.

## Runtime, Failures, and Limitations

Mean total planning time per development run was 136.01 seconds for RH_REGRET,
299.31 seconds for independent MPC-MCTS, and 182.84 seconds for coordinated
MPC-MCTS. The respective maxima were 328.20, 787.71, and 486.95 seconds.
The largest run-level event-planning p95 was 4.89, 28.44, and 7.85 seconds,
respectively. These measurements were sequential on this computer; they are
not isolated cross-machine benchmarks.

The coordinated first-decision candidate union / MILP-selected / post-repair
coverage was 54 / 25 / 74 on static `c201_21`, and 52 / 20 / 60 on static
`r201_21`, from 100 available customers each. All 24 and 30 final unserved
customers, respectively, appeared in a top-L proposal at some epoch, yet only
three from each set appeared in a selected intent. The result points to a
route-combination and repair limitation; it does not establish that all
customers were jointly feasible. Raising the candidate limit or MCTS budget
is not evidence-supported and would worsen latency. No second algorithmic
correction was made. See `results/final/DIAGNOSIS.md` for the full classification.

The 36 audited raw runs and the gate are in `results/development/`. No
holdout raw files, final statistics, or final figures are claimed. The six
development instances cannot establish a paper result.

## Conclusion

The current evidence does not support the coordination hypothesis: coordinated
MPC-MCTS has mixed paired service outcomes, worse mean unserved customers than
both development baselines, and fails the service and latency gates. The
disjoint holdout was correctly withheld, so there is no final paper claim.

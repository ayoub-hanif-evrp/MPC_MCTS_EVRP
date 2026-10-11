# Experiment Protocol

Status: final-track development. The earlier 32-iteration screen failed and is
preserved under `results/screening/`. It is not final-paper evidence.

## Frozen Development Configuration

`configs/final.yaml` declares the six development instances, six disjoint
holdout instances, physical fleet mode, common algorithm settings, and gate
thresholds. The three final methods share the same physics, scenario, fleet size,
release boundary, and deterministic seeds. MPC-MCTS methods both use Hp5, Hc1,
48 iterations, customer limit 16, top-L 5, partial charging, and parameter-free
coverage-diverse proposals. Root coverage is disabled so 48 is a strict
iteration budget. Regret repair and one service-preserving fleet-compaction pass
follow selection. No full ALNS, fleet expansion, or future information is used.

## Development

Run exactly `c101_21`, `c201_21`, `r101_21`, `r201_21`, `rc101_21`,
`rc201_21` at target DoD 0 and 0.5, scenario and algorithm seeds 0, and the
three comparison methods: 36 planned conditions. Generate each scenario once
and share it across methods. Audit all completed records and disclose
unrealized target DoD. Save manifests, raw records, and `GATE.md` under
`results/development/`.

The gate is fixed before execution: coordinated static service 6/6 complete,
dynamic mean service at least 98%, dynamic at least 5/6 complete, all target
DoDs realized, physically valid traces, and every coordinated run's event
planning p95 at most five seconds. A failed gate blocks the holdout.

If development fails, inspect the recorded reason and allow at most one
targeted correction. Candidate pruning can justify raising the limit to at
most 20; weak search selection can justify raising iterations to at most 64;
a charging failure can justify a charging-construction fix; remaining locking
can justify a flexible-suffix fix. Do not select favorable seeds, instances,
fleet sizes, or objective changes. Any correction changes source identity
and requires a fresh complete development run.

## Holdout

Only after a verified development PASS, freeze source and configuration and
run `c109_21`, `c208_21`, `r112_21`, `r211_21`, `rc108_21`,
`rc208_21` at target DoD .25/.50/.75, scenario seeds 0/1/2, algorithm seed
0, and the same three methods: 162 planned dynamic conditions. Exclude and
report only conditions whose requested DoD cannot be realized; do not
substitute a favorable seed. Run the same six instances statically at seed 0
for 18 sanity conditions. No algorithm or configuration change is permitted
after holdout begins.

## Analysis and Reporting

Primary outcome is customers unserved. Report service ratio, full-service rate,
and paired coordinated-minus-baseline wins/ties/losses, mean, median, and
95% paired bootstrap CI. Compare EV activation only at equal service and
distance only at equal service and activated EV count. Resample matched
instance/scenario pairs using 2,000 deterministic percentile-bootstrap samples
with seed 0. The six holdout instances and multiple scenarios per instance
remain a small correlated sample; intervals do not establish independent
population-level significance.

Report complete and incomplete valid runs, technical failures, ineligible
conditions, maximum and p95 event planning times, the number of repair
insertions, route compactions, and all decision-epoch coordination coverage
fields. Archive all outputs inside `results/final/`: raw manifests and records,
audited summaries, CSV/LaTeX tables, PNG figures with source CSVs, and
`FINAL_REPORT.md`. The report must say clearly whether holdout evidence
supports coordination, including negative results.

Run focused tests during development. Run the full suite once and the four
Schneider reference validations after implementation is frozen, before the
development grid. Holdout must not start when either verification or
development fails.

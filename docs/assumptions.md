# Data Facts and Experimental Assumptions

## Data and Physics

- All 92 local Schneider instances parse with no defaulted missing parameters.
  Original files are immutable; no alternate dataset was downloaded.
- Stations have common depot hours, zero demand/service and uniform linear charge
  rate. S0 is distinct from the depot even when coordinates coincide.
- One depot-to-depot tour per EV, no reloading or later reactivation after Return.
  Initial battery is Q; remaining delivery freight is C.
- Hard time windows constrain service start. Travel, early waiting, service and
  charging macro-actions are non-preemptive. Passive Wait is interruptible.
- Euclidean distances retain full precision; feasibility tolerance is 1e-8.
  Positive sub-tolerance waits are legal when they advance representable time.
- Unlimited concurrent station capacity, no traffic/queues/heterogeneous EVs.
  Planning wall time does not advance physical simulation time.
- Every dispatched action preserves a feasible final return. This is not a
  guarantee of serving all current or future requests.

## Reference and Scenarios

Five-customer subset/permutation search with Pareto full-charge repair reproduces
the four requested published counts and distances. Larger instances use multistart
insertion, targeted route reduction and relocate, with at most 24 retained labels
per customer position. This is heuristic and can overestimate minimum fleet size.
V1 used that reference fleet as a hard online cap. This is now an archived
diagnostic assumption, not the proposed V2 fleet model. V2 uses a lazy reserve
bounded by the number of customers; K_ref remains an offline benchmark.

Uniform dynamic releases under reference predecessor-departure/ready-time bounds
are an experimental choice, not the original Yang benchmark. Exact-count half-up
rounding saturates at eligible requests; realized DoD can differ from the target.
For five customers target 0.5 can mean 3/5 dynamic, not exactly one half. References
and scenarios are versioned dependencies, never inputs to an online policy.

## MPC and Coordination

The final objective is lexicographic unserved/activated/distance. MPC uses predicted
service then predicted-plus-terminal distance, followed by time/canonical ties.
UCT reward is `N - 0.5*D/[v*(depot_due-current_time)]`, with a checked feasibility
bound. Explicit lexicographic comparisons govern retained proposals.

H_p counts services, H_c=1 action. No station revisit between two predicted services;
after service revisits are allowed. Partial-charge targets are a finite set of
fractions and safe energy thresholds, not a continuous optimum. Candidate limits,
heuristic rollouts and finite search budgets may miss better feasible trajectories.

The following describes the default intent-only policy. The opt-in
[route-continuity follow-up](route_continuity_followup.md) instead uses executable
reservations and optional known-request insertion, requiring methodological review.

Intent-union coverage is an optimistic surrogate. Overlapping tails are allowed
and never reserved; their simultaneous future execution is not guaranteed. New
activation minimization can leave unused vehicles idle and does not guarantee
capacity for an unseen future request. The bounded reward fixes free-Wait dominance,
not every possible form of online myopia or charging inefficiency.

## Configurations

The CLI defaults to `configs/pilot.yaml`: H_p=3, L=3 plus fallback, 64 iterations,
candidate limit 12, UCT c=1.4, partial charging, sequential agents, seeds 0.
`debug.yaml` is an 8-iteration test config. `default.yaml` offers H_p=5/32 for a
single run, not a full grid. The compact paper method uses the common budget
selected by the predefined six-instance calibration rule, recorded in
`configs/paper.yaml`. Main execution requires a current passing calibration and
runtime gate plus `--execute`; old campaign entry points are cancelled.
Parallel processes preserve seeds/order but may be slower on small instances.
Legacy wall-clock budgets stop between full simulations. With mandatory V2 root
coverage, the initial coverage pass may exceed the wall budget; every simulation
is counted and this is not a hard realtime guarantee.

## Reporting Limits

Pilot data are small, single-seed and unbalanced across DoD. They establish
execution/integrity behavior, not statistical superiority or a controlled DoD effect.
Incomplete runs remain visible. Distance comparisons are conditional on complete
service or on equal-service/equal-vehicle paired outcomes. Vehicle marginal means
are descriptive and must not override unequal service quality.

Algorithm-seed repetitions are averaged within environment before CIs. Scenarios
of the same instance may still be correlated; use the descriptive intervals with
that limitation. No formal significance claim is automated. p95 latency means the
mean within-run decision p95, not a pooled percentile. Runtime depends on hardware.

The V1 704-condition campaign, including the full 56-instance main benchmark,
ablations and realtime study, completed. All runs passed structural audits but
all had incomplete service. Its byte-verified archive is
`results/paper_v1_fixed_fleet`; it is diagnostic, not final paper evidence.
Only the six-instance V2 diagnostic campaign is authorized. See
`results/paper_v2/PAPER_RESULTS.md`; no V2 full paper campaign has been launched.

The six large calibration cases are explicitly development instances and are not
held-out evidence of superiority. Candidate reduction is part of the method:
urgency/proximity shortlist 12 each before authoritative feasibility, 4 stations,
5 charge targets per station. Safe-return actions retain priority. Exact caches
do not relax physics. Optional unused-depot symmetry reuse is disabled because it
changed the joint search distribution and worsened distance on a validation case.
Cold offline-reference preparation is reported separately and included in campaign
runtime estimates. Concurrent throughput timings are not isolated realtime latency.

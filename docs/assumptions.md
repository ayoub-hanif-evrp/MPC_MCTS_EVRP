# Data Facts and Experimental Assumptions

## Verified Data Facts

All 92 local instances parse without supplying missing parameters. Every station
has zero demand/service and the same opening/closing interval as its depot.
`c101C5` has 5 customers, 3 stations, Q=77.75, C=200, r=1, g=3.47, v=1.
`c101C10` has 10 customers and 5 stations. `c103C15` has 15 and 5.
`r104C5` has 5 and 3; `rc105C5` has 5 and 4.
`c101_21` has 100 customers, 21 stations, Q=79.69, C=200, r=1, g=3.39, v=1.
The original files include the station S0 at depot coordinates; it is kept distinct.

## Modeling Choices

- One depot-to-depot tour per EV; return retires that EV. No reload or second tour.
- Remaining freight is modeled as a delivery resource, initialized to C. No online
  loading schedule is introduced.
- Hard customer due times constrain service start. Departure may occur later,
  provided final depot return remains feasible.
- Macro-actions are non-preemptive, including customer-window waiting.
- Passive idle time may be interrupted by release or another completion event.
- No periodic global replanning. Idle deadlines come from safe-return slack.
- Floating-point feasibility tolerance is 1e-8; coordinates/distances are unrounded.
  Positive waits shorter than that tolerance remain valid when they advance time.
- Planning computations do not consume modeled vehicle operating time.
- Every accepted action preserves a feasible final return; that condition does
  not guarantee future requests or even all current requests can be served.
- Stations have unlimited concurrent capacity, uniform linear g, and no queues.
- No station revisit is allowed between predicted customer services, preventing
  search cycles; later revisits after service are permitted.

## Scenario and Fleet Choices

The heuristic reference uses full charging, deterministic multi-start insertion,
and feasible relocate improvement. Its route count fixes K, which is never enlarged
to repair an online policy. This can overestimate the minimum feasible fleet.
An inability to construct a reference is a failure, not permission to fabricate one.

Release bounds use our reference's predecessor departures, not best-known schedules.
Uniform sampling on `(0, bound]` is our choice. Zero-bound customers cannot be
dynamic. Exact-count uses half-up rounding and saturates at eligibility; realized
DoD may differ substantially from the target. Bernoulli mode draws for all customers
and then applies eligibility. Generated scenarios and references are separate JSON
artifacts, tied to immutable benchmark SHA-256 values.

## MPC and Search Choices

Distance stage cost plus feasible-return distance is the literal current objective.
The free-Wait degeneracy remains unresolved; it is not hidden by a large reward or
penalty. The framework is not a completed proposed-method implementation until a
service requirement is selected and validated.

Prediction horizon counts customer services, not raw actions. Wait/return terminate
the prediction. Partial charging branches over actual safe energy thresholds and
fractions 0.5, 0.75, 1.0 of Q, not a continuous optimizer. This is a finite
approximation to EVRPTW-PR; MCTS cannot claim continuous-charge or routing optimality.
Full mode permits only Q targets and checks full-charge return feasibility.

Customer candidates interleave urgency and proximity after feasibility pruning.
Charging actions are generated from all remaining observed customers, even if a
customer was excluded by the direct-service candidate limit. Rollouts randomize
among up to three promising customers. UCT operates on unnormalized negative
distance, so exploration-coefficient sensitivity is a research assumption.
Top-L counts distinct root actions; the fallback is additional and separately
reported. Wall-clock budgets stop between simulations, with possible overshoot.

## Default Parameters

`configs/default.yaml` is the authoritative default configuration:

| Parameter | Default |
| --- | --- |
| experiment/scenario/reference seed | 0 / 0 / 0 |
| target DoD / selection | 0.5 / exact_count |
| algorithm | COORDINATED_MPC_MCTS |
| prediction/control horizons | 5 customer services / 1 action |
| candidate limit / top-L | 12 / 3 plus fallback |
| UCT c | 1.4 |
| budget mode / iterations | iterations / 250 |
| wall-clock limit (when selected) | 0.5 seconds |
| charging mode / fractions | partial / 0.5, 0.75, 1.0 |
| parallel agents / workers | false / 2 |
| reference starts / relocate passes | 3 / 1 |
| simulator event guard | 100000 |

`debug.yaml` uses horizon 3, 8 iterations, a 0.1-second alternative limit, and one
reference start. The `_21` smoke override uses horizon 1 and 2 iterations, solely
to test scale and termination. The full benchmark and one-factor ablation YAMLs
are not automatically executed. Suggested iteration budgets are 250, 500, 1000,
2500; supported wall-clock examples are 0.1, 0.5, 1.0, 2.0 seconds.

## Reporting Limits

Heuristic references and best-found MCTS plans are not optimality claims. The
offline reference is not an online competitor. Runtimes depend on the machine;
process parallelism need not speed up small instances. Fixed-seed logical results
exclude measured latency; wall-clock search is not strictly reproducible.
Failed runs remain in aggregates. Missing numeric metrics are not imputed.
Student-t intervals are descriptive and unavailable for n<2; no significance test
is performed. Distance without service ratio can favor policies that neglect work.

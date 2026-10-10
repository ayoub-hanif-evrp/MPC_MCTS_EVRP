# Assumptions and Limits

Status: implementation and screening. These are modeling and experimental
assumptions, not completed validation or performance claims.

## Physics

- Local Schneider benchmark files are immutable.
- Homogeneous EVs have one depot-to-depot tour, initially full battery and delivery
  capacity, no reloads, and no reactivation after return.
- Euclidean distances are unrounded. Travel time and consumption are linear in
  distance; charging time is linear in added energy.
- Hard customer windows constrain service start. Service and charging actions are
  non-preemptive; passive waiting is interruptible.
- Stations have the supported common hours/rate and unlimited concurrent capacity.
  There are no queues, stochastic traffic, or heterogeneous EVs.
- Each accepted action and retained route preserves safe depot return. This does
  not guarantee service of all current or future requests.
- Planning wall time is measured separately and does not advance simulation time.

## Fixed Fleet and Information

Every matched algorithm has exactly the same `K_ref` physical EVs. Larger-instance
offline reference fleet sizes are heuristic, not certified minimum fleets. Unused
depot vehicles remain unactivated until departure. No lazy reserve is permitted.

Online policies receive released requests, measured states, public infrastructure,
and reference fleet size only. Reference routes and future releases remain private.
Local planners cannot use customers owned by another EV. Co-timed releases and
completions are processed before planning.

## Commitments and Approximation

Each customer has at most one owner. Replay retained suffixes after feedback and
explicitly reconcile invalidated commitments. Do not retain terminal WAIT/RETURN
after the last service. Idle active EVs may wait until latest-safe-return slack is
exhausted; temporary lack of released work must not force retirement.

Finite local horizons bound new MCTS search. Retained or repaired executable
suffixes may be longer, providing persistent commitments beyond the search horizon.
This does not make MCTS an unlimited-horizon optimizer.

Candidate pruning, finite search budgets, heuristic rollouts, discrete partial
charging targets, and local insertion may miss feasible improvements. MILP
optimizes only the supplied candidate pool. Feasibility and optimal selection from
that pool do not establish global service or distance optimality.

## Scenarios and Measurement

Seeded uniform releases under predecessor-departure/ready-time bounds are the
project's Yang-inspired assumption, not a claim about the original Yang data
distribution. Record target and realized DoD, rounding on small instances, and
ineligibility when insufficient eligible requests prevent the target count.

Fixed-iteration logical behavior depends on seeds and matched dependencies.
Wall-clock search and latency depend on hardware, process load, and software.
Realtime studies run isolated from outer workers. Nominal budgets do not imply
hard realtime guarantees.

The six screening instances are development evidence, not held-out proof of
superiority. Paired bootstrap intervals must identify their resampling unit and
sample size; scenarios from one instance may be correlated. Compare vehicles only
at equal service and distance only at equal service and vehicle count. Keep valid
incomplete runs in service statistics and disclose failed, invalid, missing, and
ineligible conditions.

Historical V1/V2 results at `38d0d01` use obsolete settings and cannot be relabeled
as evidence for this method. No final validation, screening PASS, or paper claim
is established by these documents.

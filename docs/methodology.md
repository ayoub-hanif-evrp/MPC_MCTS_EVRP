# Methodology

Status: final-track development. This describes the implementation, not a
claim of experimental superiority. Current measurements live under `results/`.

## Fleet and Information

Every matched online method receives exactly `K_ref` physical EVs from a validated
offline reference (`fleet_mode: fixed_reference`). Reference routes support offline
scenario construction only. Online policies receive the fleet size, measured
states, public infrastructure, and released requests, never hidden requests,
reference schedules, or the future release calendar. Unused depot EVs activate only
after departure. There is no dynamic fleet expansion.

## Persistent Ownership and Event Cycle

Maintain `vehicle_id -> feasible soft future action/customer suffix`. Only a
currently executing action is a hard commitment. Future customers on busy routes
are temporarily frozen; a ready EV's old suffix is an incumbent candidate and
those customers return to the shared released planning pool.

1. Process all releases and action completions at the event timestamp.
2. Update physical states and replay busy routes. A physically executing action
   remains non-preemptible. An infeasible soft incumbent can be discarded.
3. Expose released customers to ready EVs, except those still frozen behind busy
   actions. Previously assigned future customers may move to another ready EV.
4. Solve finite-horizon local MPC problems approximately with MCTS, preserving each
   ready EV's old feasible route as an additional incumbent candidate.
5. Select compatible executable routes using fleet coordination.
6. Apply regret-2 repair to uncovered released requests.
7. Perform one deterministic service-preserving compaction pass, validate routes,
   dispatch first actions, and retain soft suffixes for the next event.

Selected future tails are disjoint for the current decision, not permanent owners. Trim terminal
WAIT/RETURN actions after the final service from retained commitments; safe return
must remain feasible.

An idle active EV may wait while positive latest-safe-return slack remains. Waiting
is interruptible by observed events and must not use the next hidden release.
Temporary lack of work alone must not force immediate return. Return is required
when further waiting would violate safe return and retires the EV.

## Physical Feasibility

```text
d(i,j) = hypot(x_i - x_j, y_i - y_j)
arrival = current_time + d(i,j) / v
battery_at_arrival = battery - r * d(i,j)
service_start = max(arrival, ready_j) <= due_j
service_departure = service_start + service_time_j
charge_duration = g * energy_added
```

Battery, freight capacity, service-start windows, station feasibility, and depot
closing are hard constraints. Service and recharge actions include travel and are
non-preemptive; passive waiting is interruptible. Every accepted transition must
leave a feasible depot return, possibly through charging stations. Planning,
retained-route replay, insertion, execution, and audit must use the same physics.

## MPC and MCTS

MPC defines the state, constraints, finite prediction horizon, terminal safe return,
objective, and first-action execution. MCTS approximately solves this local problem.
The prediction horizon counts customer services; charging does not consume a
service slot. The control horizon is one macro-action.

The local horizon bounds newly searched MCTS trajectories. Retained executable
suffixes and routes extended by regret repair may contain more services. Replay
such commitments for feasibility without silently extending the MCTS search
horizon or discarding existing commitments solely because they exceed it.

Keep UCT, transition/return caches, urgency/proximity customer pruning, station and
charge-target limits, partial charging, and safe-return checks. Rank local proposals
lexicographically: more predicted services, then lower predicted distance including
safe return, followed by charging/waiting/completion time and deterministic ties.
Finite budgets and pruning do not establish local or global optimality.

Final development settings are 48 simulations, prediction horizon 5, top-L 5,
customer limit 16, station limit 4, and charge-target limit 5. Maintain a valid incumbent.
Iteration mode covers the root even if its branching exceeds the nominal budget;
actual simulations and root coverage are recorded. Wall-clock deadlines take
priority over root coverage; report measured overruns without claiming hard
realtime guarantees. A single non-preemptible evaluation may overrun a deadline.

The final track uses `coverage_diverse`: it selects the normal
best proposal first, then maximizes newly covered customers relative to proposals
already selected, breaking ties by the existing quality key. No diversity
coefficient is introduced.

## Sequential MILP Coordination

For ready EV `k`, choose one candidate `p` with binary `y[k,p]`. Let `C[k,p]`
be its executable customer set:

```text
sum_p y[k,p] = 1                              for each ready vehicle k
sum_(k,p: i in C[k,p]) y[k,p] <= 1             for each customer i
```

Candidate feasibility and ownership restrictions protect busy-EV commitments too.
Solve three successive MILPs:

1. Maximize covered released customers.
2. Fix that optimum and minimize newly activated vehicles.
3. Fix both optima and minimize predicted route distance.

Selected executable tails must be customer-disjoint. Online coverage is a surrogate
for final service, not a guarantee of serving future requests. Verify the MILP
against exhaustive enumeration on small artificial cases; do not replace this
hierarchy with weighted penalties.

## Regret-2 Repair

After coordination, enumerate feasible insertion positions for each released
unassigned customer across existing routes and unused depot EVs within `K_ref`.
Evaluate insertions using the same physical model and incremental route cost.
For the cheapest two costs `c1 <= c2`, regret is `c2 - c1`.

Prioritize a unique feasible insertion, then largest regret, smallest remaining
time-window slack, earliest due date, and customer ID. Insert into the cheapest
feasible location with deterministic ties. Update routes and repeat until no more
customers can be inserted. Perform at most one final validation/reconciliation
pass before dispatch. Then transfer the entire route of an unused EV to already
activated EVs only when every customer remains covered and physically feasible.
Do not iterate coordination and repair indefinitely.

Route construction tries direct travel, bounded single-station partial-charge
bridges, then full-charge multi-station connections. It does not backtrack earlier
charging choices. Failure to construct an insertion is not a certificate that no
physically feasible insertion exists. Insertion cost is incremental predicted
distance including safe return; activation only breaks exact distance ties.

## Comparators

`RH_REGRET` retains feasible routes and applies the same regret insertion at each
event. No optional relocate pass is implemented. It uses no MCTS or
MILP and shares the fixed fleet, physics, and information boundary.

Independent MPC-MCTS resolves current candidate conflicts deterministically
without fleet MILP optimization. Coordinated MPC-MCTS adds joint selection before
repair. Record continuity and repair settings so this comparison isolates
coordination. GREEDY is a sanity baseline; `MPC_MCTS_H1` is an ablation only.

## Scenario Generation

Keep the existing Yang-inspired, reference-schedule-preserving dynamicization:

```text
upper_i = min(customer_ready_time, reference_predecessor_departure_time)
release_i in (0, upper_i] for selected eligible dynamic customers
```

Use seeded releases and generate scenarios once for all matched algorithms. Record
target and realized DoD. Exact-count selection follows its declared rounding rule;
insufficient eligible customers make the requested condition ineligible. Do not
silently substitute a lower DoD in main experiments. Offline reference-based
construction does not permit online access to reference schedules.

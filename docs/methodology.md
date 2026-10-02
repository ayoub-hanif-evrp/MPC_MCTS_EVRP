# Methodology

## Scope and State

We consider one depot, a homogeneous fixed fleet, deterministic Euclidean travel,
hard customer time windows, delivery capacity, and linear station-only charging.
Dynamic revelation is reactive: customer attributes do not exist in a policy's
observation before release. Simulator-private `GlobalState` partitions customers
into hidden, available, committed, and served sets. The partition is checked at
each event. Policies receive an immutable filtered `Observation`, not the instance
or the scenario. The static reference is used only for scenario and fleet design.

For EV k, the measured MPC state contains position, time, SOC, remaining freight,
available requests, committed request IDs, and public depot/station data. Busy
vehicles are excluded from the set of decision-ready agents. For a ready agent,
the controller builds a new `MPCPlanningProblem` on every invocation and passes
that explicit problem to `MCTSOptimizer.solve`.

## Common Transition Model

For location j reached from i at time t with SOC b and load q:

```text
d(i,j) = sqrt((x_i-x_j)^2 + (y_i-y_j)^2)
a_j = t + d(i,j)/v
b_arrival = b - r*d(i,j)
s_j = max(a_j, ReadyTime_j)
```

For service, require nonnegative arrival SOC, sufficient q, and
`s_j <= DueDate_j`. Departure is `s_j + ServiceTime_j`, and load decreases by
`demand_j`. The customer due time constrains service start, not service completion.
For recharge, select target z satisfying `b_arrival < z <= Q`; departure is
`s_j + g*(z-b_arrival)`. A zero-energy station detour is rejected. All resulting
states must retain a feasible return before depot closing. No infeasible branch
is retained by adding a penalty. `transition` raises a typed infeasibility error;
`try_transition` exposes a non-throwing feasible/rejected result.

The station graph connects nodes whose pairwise energy requirement is at most Q.
For partial charging with common station hours and common rate g, a feasible return
path of total distance D from SOC b requires total additional energy
`max(0, r*D-b)`. Its earliest return time is
`t + D/v + g*max(0, r*D-b)`. This is monotonic in D. The shortest reachable
station-network path therefore provides both minimum return distance and an
earliest-return witness under these assumptions. Charge can be allocated along
its legs without exceeding Q. The parser checks the common-hours assumptions on
actual data; it does not silently generalize this oracle to nonuniform stations.

Full-charge mode uses a separate full-charge path construction, evaluated through
the same physical engine, and prunes states with no full-charge return. It must
not rely on a partial-charge witness that it would refuse to execute.

## Explicit Finite-Horizon MPC

At epoch t, optimize a sequence `U_k = (u_k^0, ..., u_k^m)` of macro-actions:
ServeCustomer, RechargeAt, Wait, or ReturnDepot. The prediction horizon H_p counts
customer services. Charging may occur between services without consuming that
count. Wait and Return terminate a prediction. No station is revisited between
two predicted customer services, ensuring a finite tree; stations may be revisited
after a service. Main H_p is 5; supported ablations include 1, 3, 5, and 8.

The deterministic model is `x_(j+1) = f(x_j,u_j)` from the common engine. Physical
constraints and safe return are enforced during candidate generation, prediction,
rollout, and evaluation. The requested distance objective is:

```text
J_k(U_k) = sum_j d(u_k^j) + D_safe_return(x_end)
```

Charging time, waiting time, and completion time break local equal-distance ties.
The control horizon is exactly H_c=1. After coordination only `u_k^0` becomes a
plant commitment. No predicted tail is stored as a customer reservation or
automatically dispatched later.

### Unresolved Service Requirement

The distance expression alone does not express the VRP requirement to serve
customers. An unused EV at the depot can Wait at zero distance, with zero terminal
return distance. Consequently the specified coordinator chooses all-Wait actions
even when positive-distance service plans exist. This is a mathematical degeneracy,
not evidence that a zero-distance route is a useful solution. It is covered by a
regression test and appears in all coordinated development smoke runs.

A possible resolution is lexicographic service feasibility/progress followed by
distance, with an explicitly defined coverage rule. That changes the supplied
selection formulation and is awaiting the user's choice. No arbitrary service
reward or large penalty has been included in the current distance-only method.
The project must not be marked research-complete until this issue is resolved and
the proposed routing method is rerun and audited.

## MCTS Numerical Optimizer

Each node holds a copy-safe complete local predicted state, remaining observed
customers, service depth, visited stations since the previous service, action path,
and cumulative distance. Selection uses
`mean_reward + c*sqrt(log(parent_visits)/child_visits)`; unvisited children receive
infinite selection priority. A simulation's reward is negative J, so larger reward
means smaller predicted distance. Backpropagation updates every selected ancestor.

Customer expansion interleaves urgency and proximity rankings after physical
feasibility filtering, up to `candidate_limit`. Charging targets are never removed
by that customer limit. The partial target set contains Q/2, 3Q/4, Q, energy to
actual station/depot continuations, and energy to a customer plus its nearest safe
node. Infeasible, duplicate, and nonpositive charge amounts are discarded.

Rollouts randomize among up to three promising urgency/distance customer actions;
when direct service is unavailable they prefer a charging action that enables an
observed customer. They use no future-request model. Each simulation ends at H_p
customer services or an idle/return leaf. Fixed iterations give reproducible work
budgets; wall-clock limits are checked between complete simulations and may
overshoot by one simulation.

MCTS retains the best-found trajectory for each distinct first action, then returns
at most L proposals. Each proposal records estimated cost, visits, predicted end
state, customer sequence, charging actions, distance, and tail. The safe fallback
is separate from L. Root visits/mean rewards, iterations, expanded nodes, and elapsed
time are recorded per invocation. No optimality is asserted.

## First-Action Coordination

For proposals p from each ready EV k, choose binary variables y_kp:

```text
minimize sum_(k,p) J_kp * y_kp
sum_p y_kp = 1                                      for each ready EV k
sum_(k,p:first(p)=Serve(i)) y_kp <= 1                 for each customer i
y_kp in {0,1}
```

Already committed customers are inadmissible. Each service-first proposal uses a
shared customer column; each EV's non-customer alternatives use its private column.
The resulting rectangular assignment is solved by successive shortest augmenting
paths. No station capacity or plug conflict is introduced. Deterministic sorted
ordering resolves exact ties. Coordinator correctness is checked against exhaustive
enumeration on small random cases. The unresolved free-Wait issue above applies to
this exact stated formulation.

The independent baseline processes vehicles in ID order, selecting the first
nonconflicting local alternative and recording duplicate initial proposals. It
does not optimize the joint assignment. GREEDY uses the same conflict rule and
physical engine with one-service urgency/proximity proposals.

## Events, Commitments, and Parallelism

At a timestamp the simulator reveals all releases and completes all finished
actions before taking observations. Service includes early time-window waiting;
charging includes travel to station. Both remain busy and non-preemptive. On service
dispatch the first customer moves available -> committed; only completion moves it
committed -> served. Waiting is passive and interruptible. Its deadline is depot
closing minus the public safe-return duration, never the next hidden release.

Ready agents plan independently from the same immutable observation. Optional
process workers receive only agent/controller, measured vehicle state, observation,
and a derived seed. Seeds hash `(experiment_seed, scenario_seed, epoch, vehicle_id)`.
Results are collected in vehicle order before coordination, so worker completion
order cannot alter fixed-iteration logical results. Planning latency is measured
wall time but does not advance simulation time.

## Reference and Dynamicization

The static reference sorts customers by due time (first start), perturbs order with
explicit seeded jitter in additional starts, evaluates feasible insertions at all
route positions, and opens a new route only when no existing insertion succeeds.
Battery-infeasible gaps use full-charge station repair. Feasible relocate moves
improve route count then distance. This is a constructive heuristic, not ALNS or a
best-known solution; failures are explicit. All route evaluations and final replay
use the common transition model. Its route count fixes K for every algorithm.

Following the availability-bound idea in Yang et al., our generated scenarios use
`upper_i = min(ReadyTime_i, predecessor_departure_i)` from this heuristic reference.
Exact-count selection targets half-up `round(DoD*n)` eligible customers, saturating
at the eligible population; Bernoulli draws are made independently for all
customers, with zero-bound requests necessarily kept static. A selected eligible
request receives a uniform sample in `(0, upper_i]`. Actual counts and bounds are
saved. The complete reference remains feasible under these releases.

This is **reference-schedule-preserving dynamicization inspired by Yang et al.**,
not the original Yang benchmark. Uniform sampling, the reference heuristic,
partial-charge discretization, and online policy choices are our assumptions.
The four methodological references and original DOIs are listed in README.md.

## Evaluation and Integrity

Run records retain incomplete service, failed execution, and exceptions. Feasibility
requires all customers served and every EV safely returned; legal individual actions
alone are insufficient. Trace replay checks transitions, disclosure times, unique
service, non-preemption, commitments, and terminal depot states. Aggregation shows
service ratio alongside distance and retains failure counts. Descriptive confidence
intervals do not establish superiority, and one smoke seed supports no significance
claim. Repeated algorithm seeds on one scenario are not independent environmental
replications; formal inference requires an explicitly chosen replication unit.

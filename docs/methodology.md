# Methodology

## Scope and Information Boundary

The V1 physical model used a fixed homogeneous fleet, one depot-to-depot tour per EV,
delivery capacity, hard service-start windows, Euclidean travel, and linear charging.
GlobalState privately partitions hidden/available/committed/served requests. Agents
receive only measured vehicle state, observed available requests, committed IDs,
and public infrastructure. Reference routes and future release times are unavailable
to MPC, MCTS, rollouts, terminal costs, workers, and the coordinator.

At each event, process all releases and completions at the timestamp, form a common
observation for ready vehicles, run their controllers, coordinate proposals, and
dispatch only first actions. A Serve includes travel, early waiting, and service;
Recharge includes travel and positive-energy charging. Both are non-preemptive.
Busy vehicles cannot replan. Passive Wait can be interrupted by another event.
Its public deadline is latest safe return, not the next hidden release.

## Physical Feasibility

```text
d(i,j) = hypot(x_i-x_j, y_i-y_j)
arrival = t + d(i,j)/v
SOC_arrival = b - r*d(i,j)
service_start = max(arrival, ReadyTime_j) <= DueDate_j
service_departure = service_start + ServiceTime_j
charging_departure = arrival + g*(target_SOC - SOC_arrival)
```

Battery and freight capacities are hard constraints; invalid branches are pruned,
not retained with a penalty. Windows constrain service start, not completion. Every
accepted action must leave a safe return before depot closing. Return retires an EV.
Charging is only at station nodes, including S0 coincident with the depot.

For uniform station hours and charging rate, a feasible station-network return of
total distance D has earliest completion `t + D/v + g*max(0,r*D-b)`. This is monotone
in D. A shortest reachable path with each later leg requiring at most Q supplies a
partial-charge return witness; charging is allocated along the path. The parser
checks the uniform-hours assumptions. Full-charge mode checks a separate full-charge
return construction. Neither oracle is generalized to heterogeneous rates/queues.

## Hierarchical Objective

For final fleet execution minimize lexicographically:

```text
(number of unserved customers, number of activated EVs, total travel distance).
```

At an MPC epoch, H_p counts predicted customer services. Charging does not consume
this horizon. H_c is exactly one macro-action. Wait and Return end a prediction;
station revisits are prohibited between services, but allowed after service. The
local deterministic MPC problem ranks feasible trajectories by:

```text
(-N_k, D_k + D_safe_return(x_end), charging_time, waiting_time,
 completion_time, canonical_action_sequence).
```

N_k counts distinct observed customers in the trajectory. The old distance-only
formulation admitted unused-depot Wait at zero cost, so all-Wait minimized cost
while ignoring the routing task. Service-first ranking explicitly repairs that
mathematical omission. Local service progress and joint intent coverage are online
surrogates, not a proof of minimizing final unserved customers.

## MCTS as Numerical Optimizer

Each EVAgent owns an MPCController that builds MPCPlanningProblem. MCTSOptimizer
only searches this supplied problem. UCT maximizes mean reward plus
`c*sqrt(log(parent_visits)/child_visits)`; unvisited children have infinite priority.
The backed-up rollout reward is:

```text
B_k = v * max(0, depot_due - current_time)
d_normalized = (D_k + D_safe_return) / B_k   [0 if B_k=0]
R_k = N_k - 0.5*d_normalized.
```

Hard terminal feasibility bounds distance by B_k because travel consumes at least
D/v time; charging and waiting consume additional nonnegative time. The code checks
the bound, tolerates floating-point error, and clips only that tiny upper overshoot.
Thus normalized distance is in [0,1], and one additional service improves reward by
at least 0.5. The coefficient is bounded, not an arbitrary large service penalty.
UCT averages guide exploration, but explicit lexicographic keys retain best-found
trajectories per root action and select top-L. Charge-first trajectories receive
credit for their downstream observed service. Top-L counts distinct first actions;
a separately retained feasible fallback is always available.

Customer expansion first applies cheap necessary capacity, energy and earliest
arrival checks, then interleaves the 12 most urgent and 12 nearest customers.
Only that union receives full transition/return checks, retaining at most 12 service
actions. Charge lookahead uses a corresponding observed-customer shortlist without
requiring current direct battery reachability. At most four reachable stations are
retained, prioritizing the required safe-return station, nearest stations and low
detour to urgent work. At most five targets per station include exact safe-return
and shortlisted-service energy thresholds plus Q/2, 3Q/4 and Q. Zero increments
and EPS-equivalent targets are removed. The required safe-return action survives
the shortlist bounds. Distinct energy/time tradeoffs are not falsely dominated.
This is explicit MCTS action-space reduction, not a completeness guarantee.
Rollouts randomize among up to three promising services or charge to enable an
observed shortlisted service. No future requests are sampled.
Partial charge is discretized, not continuously optimized. Search budgets are fixed
iterations or wall-clock checks between complete simulations (possible overshoot).
MCTS plans are best-found feasible plans, never claimed optimal.

Exact matrices, state/action transition caches and incremental proposal construction
remove duplicate computation without changing feasible transitions. The 16-iteration
paper budget was selected once using the predefined six-instance calibration rule,
not tuned per test instance. Optional reuse for identical unused-depot states is
disabled: sharing the first vehicle's stochastic search changes joint proposals.

Proposals store vehicle, first action, full action sequence, customer sequence and
unique set/count, predicted/terminal/total distance, charge/wait/completion times,
new activation flag, root visits, value estimate, and predicted end state.

## Intent-Aware Coordination

Let P_k be ready EV k's proposals, C_kp their observed customer sets, a_kp indicate
a first service/charging departure by a previously unused EV, and J_kp total
predicted distance including terminal return. Choose binary y_kp and customer z_i:

```text
sum_p y_kp = 1                              for each ready EV
sum_(k,p:first=Serve(i)) y_kp <= 1           immediate commitments
z_i <= sum_(k,p:i in C_kp) y_kp
y_kp <= z_i                                for every i in C_kp
y_kp, z_i in {0,1}
```

Committed customers cannot be first actions and are excluded from available intent
sets. Hidden or otherwise unavailable tail customers cause rejection. Linking
constraints make z exactly the union of selected intentions; overlap is legal and
counts once. Recharge/Wait/Return have no customer-conflict constraint. Station
capacity is unlimited. New activation is measured by actual first-action departure,
not by hypothetical tail actions or merely selecting an idle depot vehicle.

Three sequential [SciPy MILPs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)
are solved with integer variables and zero relative MIP gap:

1. Maximize sum_i z_i; fix optimum coverage with an equality.
2. Minimize sum a_kp*y_kp; fix optimum activations with an equality.
3. Minimize sum J_kp*y_kp.

No arbitrary weighted combination or production exhaustive enumeration is used.
Sorted vehicle/proposal order and deterministic solver behavior make ties stable;
this does not assert identical alternate optima across solver versions. Small
random exhaustive tests independently check the three-stage objective.
Only the first action is dispatched; tails are recomputed after feedback and never
reserve customers. Shared intentions can be optimistic about future joint service.

Independent MPC selects local alternatives in vehicle-ID order to avoid duplicate
first commitments, without joint optimization. Greedy uses the same conflict rule
and physical engine with myopic urgency/proximity and charging repair. H1 keeps
coordination but truncates predicted service horizon to one.

## Reference Validation and Dynamicization

References must serve all customers, minimizing route count before distance. For
up to five customers, all subset/permutation customer orders are evaluated and a
subset partition DP chooses routes. Charging repair propagates nondominated
time/SOC/distance labels, exploring charging before later customers even when a
direct leg is feasible. For larger instances, multistart insertion, targeted route
elimination by reinsertion, and relocate use the same route evaluator, capped at
24 inter-customer labels. This cap and the customer-order heuristic limit quality.
An exact bounded prefix-frontier cache avoids evaluating identical customer prefixes
again; cache eviction changes computation only, not labels or their order. Cold
reference preparation remains offline and is included in campaign runtime estimates.

External metadata come from Schneider, Stenger and Goeke, Technical Report 02/2012,
Table 3, CPLEX column (precursor to Transportation Science 2014):
[author report](https://web4.ensiie.fr/~faye/mpro/MPRO_reseau/Projet_2020/The%20electric%20vehicle%20routing%20problem%20with%20time%20windows%20and%20recharging%20stations.pdf).

| Instance | Published EVs | Published distance | Reproduced distance |
| --- | ---: | ---: | ---: |
| c101C5 | 2 | 257.75 | 257.7474518642 |
| c103C5 | 1 | 176.05 | 176.0544331488 |
| c206C5 | 1 | 242.56 | 242.5556517150 |
| c208C5 | 1 | 158.48 | 158.4806595843 |

Validation requires matching route count and distance within 0.011 published units.
For c206C5 the report's heuristic column is 242.55 while CPLEX is 242.56; the local
full-precision value rounds to 242.56. The reference checks do not establish
large-instance optimality. Failure blocks the main CLI gate.

K is the constructed reference route count, fixed across online algorithms. A
customer's release bound is `min(ready_i, predecessor_departure_i)`. Seeded uniform
releases in `(0,bound]` preserve that reference's feasibility. Exact-count uses
half-up rounding with saturation; Bernoulli draws all customers then applies
eligibility. Both target and realized dynamicity are reported. The method is
reference-schedule-preserving dynamicization inspired by Yang, not the original
Yang dataset or a claim that Yang used this sampling distribution.

Base SHA, reference hash, reference-solver version, generator version, and objective
version bind scenarios. Old schemas/dependencies are rejected; current scenarios
are generated once and read for each algorithm. No original dataset is altered.

## Measurement and Reporting

Planning latency includes local proposals and coordination but does not advance
simulation time. Fixed-iteration seeds derive from experiment seed, scenario seed,
epoch and vehicle. Process workers receive only filtered observations; results are
collected in vehicle order. Wall-clock experiments are a separate study.

Disk audits replay transitions, continuity, releases, commitments, selected and
candidate tails, uniqueness, safe returns, primary/secondary totals, schemas and
dependency/configuration hashes. Duplicate IDs, NaNs and structural errors are
reported and excluded from scientific aggregates. Failed/incomplete runs remain in
failure tables; incomplete but physically valid runs enter service statistics.

Report service first, then vehicle usage, then conditional distance. Distance
figures use complete-service runs only. Paired vehicles require equal unserved
counts; paired distance requires equal unserved and activated-vehicle counts.
Pair on instance, scenario hash/seed, algorithm seed, source revision and study;
ambiguous duplicate configurations are reported rather than cross-joined.

Average algorithm seeds within instance/scenario before means, medians, sample SD,
and Student-t 95% CIs over environmental observations. This prevents treating seed
repeats as independent environments; scenarios within an instance may still be
correlated, so intervals are descriptive, not formal inferential evidence. Report
eligible-pair and environment counts. No automatic significance tests are used.
Runtime p95 summaries are averages of within-run p95, not pooled percentiles.

Raw precision is retained. Publication tables round only on export. Figures are
CSV-driven 300-dpi PNG only, with exact data; the representative configuration is
fixed before outcomes are inspected. Unrun ablations are marked empty, not filled
from unrelated pilot variations. The main benchmark has not been executed.

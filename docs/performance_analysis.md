# Performance Correction

The final measured launch decision, full calibration table and runtime estimate
are in [performance_results.md](performance_results.md). The profile table below
records the first optimized pass; final profiles additionally include exact
escape-geometry caching, with no change to the bounded action set.

The 17,017-job design is cancelled. Its 58 completed results are preserved under
`results/campaigns/final`; no further jobs from that design are authorized.
The replacement campaign must not run until profiling, calibration, integrity
checks, and the runtime gate have passed and the user explicitly launches it.

## Measurement Protocol

Isolated c101_21, DoD 0.5, scenario/algorithm seeds 0, coordinated MPC-MCTS,
partial charging, Hp 5, L 3, budgets 8/16/32. cProfile plus explicit stage timers
and candidate counters measure complete simulations, with separate audit and
serialization timings. Profiling times include instrumentation overhead;
unprofiled timings determine the performance gate. Raw profiling artifacts are
written to the local SSD outside OneDrive.

## Predefined Budget Rule

Use exactly c101_21, c201_21, r101_21, r201_21, rc101_21, rc201_21, DoD 0.5,
scenario/algorithm seeds 0, and budgets 8/16/32/64. The reference budget is the
one with the highest median service count (largest budget breaks a tie).
Select the smallest budget with median service no more than one customer below
that reference, and distance at most 1.05 times the reference on every paired
instance with equal service AND equal activated-vehicle count. A candidate with
no such pairs cannot establish the distance condition. The reference compares
to itself. Missing/failed calibration, ambiguous selection, or a non-finite
comparison defaults to 32 with the reason recorded; it never silently removes
failed rows. Incomplete service is not an execution failure.

These rules were specified before running the optimized calibration. Calibration
instances are disclosed development cases, not an independent holdout sample.

## Measured Bottlenecks

All values below are complete c101_21 runs, not one agent call. Cumulative
cProfile times overlap and must not be added together.

| Iterations | Before profile s | After profile s | Mean branch before/after | Max branch before/after | Transition calls before/after |
| ---: | ---: | ---: | --- | --- | --- |
| 8 | 59.656 | 3.292 | 179.80 / 12.66 | 1148 / 34 | 3,911,308 / 48,231 |
| 16 | 145.323 | 10.205 | 200.96 / 13.70 | 1156 / 34 | 8,720,860 / 107,017 |
| 32 | 464.286 | 25.310 | 229.53 / 15.33 | 1337 / 34 | 20,343,769 / 250,625 |

At 32 iterations, charging candidates generated fell from 4,831,608 to 162,038;
retained charge actions fell from 3,103,870 to 124,140. Exact customer-feasibility
checks considered 676,919 customers before and 55,413 after. Counts are across
all visited states and agents; the policy trajectories differ after pruning.

| Component at 32 iterations | Before seconds | After seconds |
| --- | ---: | ---: |
| actions(), cumulative | 284.331 | 20.102 |
| customer feasibility, explicit timer | 10.321 | 3.232 |
| customer ranking, explicit timer | 3.104 | 0.695 |
| charging target generation, explicit timer | 58.510 | 5.603 |
| transition(), cumulative | 349.008 | 10.294 |
| escape(), cumulative | 152.061 | 7.649 |
| terminal_cost(), cumulative | 1.019 | 0.185 |
| proposal replay/construction, cumulative | 4.011 | 0.468 |
| MCTS selection plus expansion | 8.080 | 0.583 |
| MCTS expansion (included in preceding row) | not separately instrumented | 0.066 |
| MCTS rollout | 450.536 | 22.673 |
| MCTS backpropagation | 0.016 | 0.011 |
| result conversion and gzip serialization | 0.269 | 0.198 |

The optimized selection/action-initialization portion is 0.517 s after subtracting
expansion. The baseline phase timer grouped selection and expansion; it does not
support an honest separate baseline expansion estimate. cProfile records and
per-agent simulation counts are preserved in `results/performance/*_32.json`.
The baseline had 246 agent replans / 103 epochs; optimized had 226 / 112.

The unprofiled baseline took **167.988 s**. Explicit coordinator timing was
**0.824 s over 103 epochs (0.49%)**; the three sequential MILPs are unchanged.
Repeated identical unused-depot searches accounted for **30.688 s**, 15 searches
beyond the first search in each identical-state group. This is measured duplicated
effort, not a promised speedup from symmetry reuse.

## Implemented Changes

- Immutable full-precision distance/travel-time/energy matrices are built at
  instance load. Coordinate-pair caches are prewarmed; no rounding is introduced.
  Read-only ID maps replace transition-model linear scans. Complete instance
  geometry remains outside the observation supplied to agents.
- Cheap capacity, battery, arrival-time and slack checks create the interleaved
  union of the 12 most urgent and 12 nearest candidates. Only this pool receives
  authoritative transition and safe-return checks. Charging lookahead uses the
  same bounded pool, with direct-battery screening deferred until after charging.
- Station shortlist limit is 4, target limit is 5. The mandatory escape station
  and target have priority, followed by proximity and low detour to urgent work.
  Meaningful SOC targets are the exact minimum safe-return energy, a minimum
  shortlisted-service-plus-safe-node reserve, 50%, 75%, and 100% capacity.
  Nonpositive charge increments and EPS-equivalent targets are eliminated before
  materializing actions. Distinct energy/time tradeoffs are not incorrectly called
  dominated. The authoritative transition/escape oracle still filters every action.
  Default branching is bounded by 12 services + 20 charges + wait/return = 34.
- Per-planning-problem caches key transitions by the complete immutable state and
  action, with observation/configuration fixed by that problem. Both successes and
  infeasibilities are cached. Ranking reuses the evaluated transition.
- Rollouts carry state and cumulative distance forward. Proposal construction
  reads service/charge/wait accumulators from the predicted state and computes the
  terminal cost once. Final candidates reuse the best already-built proposal.
- `trace_level=full|summary|none` never changes decisions. Summary omits candidate
  trees but retains executed steps, event commitments, selected plans, search
  statistics, and compact candidate-intent evidence. None omits planning-detail
  traces, not the minimal physical/information evidence needed for audits.
- BLAS threads remain one; throughput uses outer workers only. Realtime jobs run
  after the outer pool exits. Every record identifies its execution profile and
  timing summaries/pairs separate isolated from concurrent measurements.
- Runtime outputs can live under `%LOCALAPPDATA%/EVRP`, outside OneDrive. Atomic
  JSON replacement retries transient Windows permission errors; completed reports
  and PNG/CSV figures are copied back only after reporting.
- Cold reference profiling exposed repeated prefix frontiers. A bounded 512-entry
  LRU now reuses the exact Pareto frontier for an identical instance, vehicle ID,
  label limit and customer prefix. The insertion/repair method, label cap, random
  order, tie order and reference objective are unchanged. Geometry-only safe-return
  paths are cached by exact location, SOC and infrastructure; actual state time is
  applied afterwards. Seven full route traces matched exactly (7.859 -> 0.960 s;
  252,755 -> 62,482 transitions). Full reference-hash checks are reported separately.
- Reference/scenario preparation is grouped by instance and executed in an outer
  pool. A single worker owns all scenarios of an instance, so shared reference and
  scenario files never have competing writers. Setup time is included in runtime
  estimation rather than being hidden before the timed experiment.

Action-space reduction changes the search policy, not the objective, information
structure or feasibility rules. Service at 8/16/32 changed from 67/60/61 to
64/67/66; no dominance claim is inferred from one instance. With action-space
reduction disabled, exact optimizations reproduced every executed transition and
event in saved seeded c101C5, r104C5 and rc105C5 baseline traces.

## Symmetry Finding

Optional `symmetry_reuse` requires identical complete unused-depot state (except
vehicle ID), observation, and MPC configuration. Active/busy/finished vehicles
are excluded and proposal vehicle IDs are rebound. Shared search uses the first
vehicle's seed, changing the joint proposal distribution. It is **disabled** in
all paper and calibration configurations.

On r104C5 (8 iterations), both variants served 5 customers using 2 EVs, but distance
increased from 139.945 to 167.619 with reuse. rc105C5 changed from 168.052 to 169.459;
c101C5 retained its primary outcomes but changed the physical trace. All variants
passed replay and information audits. These findings do not justify enabling reuse.

## Compact Study Membership

| Study | Table conditions | Unique within study | Additional after preceding studies |
| --- | ---: | ---: | ---: |
| A: all 56 instances, DoD .5, four algorithms | 224 | 224 | 224 |
| B: 12 balanced instances, four DoDs, two scenario seeds, four algorithms | 384 | 384 | 336 |
| C: six development instances, three MCTS algorithms, five algorithm seeds | 90 | 90 | 72 |
| D: six development instances, one factor at a time | 84 | 60 | 48 |
| E: c103C15/c101_21/r101_21, four wall budgets, algorithm seeds 0/1 | 24 | 24 | 24 |
| Total | 806 | 704 across all studies | 704 |

The 24 calibrated budget conditions are already members of A/D and can be reused
after independent disk audits and exact source/scenario/configuration matching.
Membership is separate from scientific job identity; derived study views record
their source run ID instead of recomputing conditions or treating copies as new
independent replications. Realtime measurements remain separate from throughput.
The fixed 15-customer case is c103C15, present in the supplied benchmark.

Calibration outcomes, selected budget, resource measurements, and the final
prelaunch estimate are generated in `results/performance`. No new paper campaign
is launched by profiling, calibration, or `evrp.cli estimate`.

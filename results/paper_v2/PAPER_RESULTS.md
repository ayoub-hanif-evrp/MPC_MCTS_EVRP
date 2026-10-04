# V2 Diagnostic Results: Not Final Paper Results



**STOPPED AFTER THE DIAGNOSTIC CAMPAIGN. Full paper execution is blocked pending user review.**



**Scientific and computational gate FAILED.** The mechanical calibration rule selected96 simulations, but that is not an accepted final configuration. Worst coordinated diagnostic: c201_21, DoD=0, 6097.92s (101.63min) planning and23,943 WAIT selections. Repeated short WAITs can still create long idle spells despite the per-action bound. See the [idle-spell audit](tables/markdown/idle_spells.md). The coordinated method also misses customers that Independent serves and uses far more EVs than the reference. Do not launch a full campaign or claim a final budget.

## Experimental Setup

Six development instances, DoD 0/.5, scenario/algorithm seeds0, partial charging, Hp5, L3, customer/station/target limits12/4/5. Selected nominal MCTS budget **96**, mandatory root coverage charged to actual simulations. 2 outer workers; concurrent timings, BLAS1. 66 unique online diagnostics plus12 offline controls. No V2 all-56-instance campaign, seed-robustness study or realtime run.



## Scientific Gate

| Question | Answer |
| --- | --- |
| Oracle complete service? | 12/12 complete |
| Coordinated static complete service? | 4/6 complete; mean service 98.17% |
| Flexible fleet improves service? | Mean paired gain 44.50 customers at DoD=.5; mechanism is not a cap-only ablation |
| Extra dynamic vehicles? | Mean 45.67 beyond K_ref |
| Coordination improves service? | Mean coordinated-minus-independent unserved 1.25 across12 paired controls; inspect family rows |
| Root actions evaluated? | Coverage min 1.000; minimum root visits 1 |
| V2 full campaign authorized? | NO. Scientific review required; executor blocked. |


## Offline Feasibility Control

| instance | DoD | customers_served | K_ref | total_distance | final_return_feasibility |
| --- | --- | --- | --- | --- | --- |
| c101_21 | 0.000 | 100 | 13 | 1433.14 | True |
| c101_21 | 0.500 | 100 | 13 | 1433.14 | True |
| c201_21 | 0.000 | 100 | 5 | 774.58 | True |
| c201_21 | 0.500 | 100 | 5 | 774.58 | True |
| r101_21 | 0.000 | 100 | 20 | 1939.69 | True |
| r101_21 | 0.500 | 100 | 20 | 1939.69 | True |
| r201_21 | 0.000 | 100 | 4 | 1862.55 | True |
| r201_21 | 0.500 | 100 | 4 | 1862.55 | True |
| rc101_21 | 0.000 | 100 | 21 | 2471.40 | True |
| rc101_21 | 0.500 | 100 | 21 | 2471.40 | True |
| rc201_21 | 0.000 | 100 | 5 | 2444.40 | True |
| rc201_21 | 0.500 | 100 | 5 | 2444.40 | True |

OFFLINE FEASIBILITY ORACLE. Replays the reference that generated each scenario. Contains future route information; never an online competitor. All12 independently audited for released-before-dispatch and physical replay.


## Main Benchmark Results

This is the six-case dynamic diagnostic subset, not a new56-instance benchmark.

| Family | Algorithm | n | Service_pct | Unserved | EVs | Distance | Planning_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | Greedy | 1 | 100.00 | 0.000 | 100.00 | 5799.98 | 0.099 |
| C1 | Independent | 1 | 100.00 | 0.000 | 100.00 | 6185.25 | 16.36 |
| C1 | Coordinated | 1 | 100.00 | 0.000 | 58.00 | 4214.56 | 568.49 |
| C2 | Greedy | 1 | 100.00 | 0.000 | 100.00 | 5942.81 | 0.068 |
| C2 | Independent | 1 | 100.00 | 0.000 | 100.00 | 5999.95 | 7.51 |
| C2 | Coordinated | 1 | 100.00 | 0.000 | 55.00 | 3831.72 | 2517.06 |
| R1 | Greedy | 1 | 100.00 | 0.000 | 97.00 | 5262.77 | 0.193 |
| R1 | Independent | 1 | 100.00 | 0.000 | 100.00 | 5313.40 | 17.30 |
| R1 | Coordinated | 1 | 99.00 | 1.00 | 75.00 | 3851.40 | 160.25 |
| R2 | Greedy | 1 | 100.00 | 0.000 | 100.00 | 4989.42 | 0.080 |
| R2 | Independent | 1 | 100.00 | 0.000 | 100.00 | 5063.12 | 6.58 |
| R2 | Coordinated | 1 | 100.00 | 0.000 | 44.00 | 3052.64 | 517.54 |
| RC1 | Greedy | 1 | 100.00 | 0.000 | 96.00 | 6624.58 | 0.091 |
| RC1 | Independent | 1 | 100.00 | 0.000 | 98.00 | 6839.09 | 10.80 |
| RC1 | Coordinated | 1 | 97.00 | 3.00 | 65.00 | 4721.95 | 131.02 |
| RC2 | Greedy | 1 | 100.00 | 0.000 | 100.00 | 6617.54 | 0.051 |
| RC2 | Independent | 1 | 100.00 | 0.000 | 100.00 | 6769.10 | 4.85 |
| RC2 | Coordinated | 1 | 100.00 | 0.000 | 45.00 | 4453.88 | 597.69 |
| Overall | Greedy | 6 | 100.00 | 0.000 | 98.83 | 5872.85 | 0.097 |
| Overall | Independent | 6 | 100.00 | 0.000 | 99.67 | 6028.32 | 10.57 |
| Overall | Coordinated | 6 | 99.33 | 0.667 | 57.00 | 4021.02 | 748.68 |

DoD=.5. One development instance per family; Overall is six instances per method. Distance/EV means are descriptive, never ranked ahead of service. No bold winners or significance claims.


![service by family](figures/main/service_by_family.png)

## Static Sanity

| Instance | Algorithm | Served | Unserved | K_ref | EVs | Distance | Planning_s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| c101_21 | Greedy | 100 | 0 | 13 | 100 | 5799.98 | 0.064 |
| c101_21 | Independent | 100 | 0 | 13 | 100 | 7198.09 | 22.99 |
| c101_21 | Coordinated | 100 | 0 | 13 | 76 | 4782.65 | 709.67 |
| c201_21 | Greedy | 100 | 0 | 5 | 100 | 5942.81 | 0.047 |
| c201_21 | Independent | 100 | 0 | 5 | 100 | 6519.92 | 16.45 |
| c201_21 | Coordinated | 100 | 0 | 5 | 100 | 6368.65 | 6097.92 |
| r101_21 | Greedy | 100 | 0 | 20 | 99 | 5210.01 | 0.096 |
| r101_21 | Independent | 100 | 0 | 20 | 100 | 6055.09 | 20.17 |
| r101_21 | Coordinated | 92 | 8 | 20 | 80 | 4180.32 | 145.37 |
| r201_21 | Greedy | 100 | 0 | 4 | 100 | 4989.42 | 0.046 |
| r201_21 | Independent | 100 | 0 | 4 | 100 | 5291.74 | 18.24 |
| r201_21 | Coordinated | 100 | 0 | 4 | 67 | 3787.12 | 1081.78 |
| rc101_21 | Greedy | 100 | 0 | 21 | 100 | 6859.37 | 0.086 |
| rc101_21 | Independent | 100 | 0 | 21 | 100 | 8404.00 | 23.52 |
| rc101_21 | Coordinated | 97 | 3 | 21 | 73 | 4718.73 | 135.37 |
| rc201_21 | Greedy | 100 | 0 | 5 | 100 | 6617.54 | 0.031 |
| rc201_21 | Independent | 100 | 0 | 5 | 100 | 6876.55 | 6.63 |
| rc201_21 | Coordinated | 100 | 0 | 5 | 70 | 5283.93 | 690.69 |


## Fleet Diagnosis

| Instance | K_ref | V1_served | V2_hard_served | V2_reserve_served | Hard_EVs | Reserve_EVs | Extra_EVs | Hard_distance | Reserve_distance | Hard_planning_s | Reserve_planning_s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c101_21 | 13 | 67 | 67 | 100 | 13 | 58 | 45 | 1695.39 | 4214.56 | 27.07 | 568.49 |
| c201_21 | 5 | 40 | 28 | 100 | 5 | 55 | 50 | 410.41 | 3831.72 | 10.09 | 2517.06 |
| r101_21 | 20 | 64 | 66 | 99 | 20 | 75 | 55 | 1593.67 | 3851.40 | 22.66 | 160.25 |
| r201_21 | 4 | 48 | 47 | 100 | 4 | 44 | 40 | 848.77 | 3052.64 | 20.83 | 517.54 |
| rc101_21 | 21 | 78 | 79 | 97 | 21 | 65 | 44 | 2118.71 | 4721.95 | 23.76 | 131.02 |
| rc201_21 | 5 | 42 | 42 | 100 | 5 | 45 | 40 | 1203.30 | 4453.88 | 11.68 | 597.69 |

Same scenarios/seeds. V2 hard/flexible runs share the selected budget and coverage/wait rules; flexible treatment also changes reserve proposal sharing and busy-tail coverage, so it is a fleet-policy comparison, not a cap-only causal estimate. V1 uses budget16 and different search/wait rules; its column is descriptive provenance only.


## Dynamicity Analysis

| Algorithm | DoD | n | Service_pct | CI_half_width | EVs | Planning_s |
| --- | --- | --- | --- | --- | --- | --- |
| Greedy | 0.000 | 6 | 100.00 | 0.000 | 99.83 | 0.062 |
| Greedy | 0.500 | 6 | 100.00 | 0.000 | 98.83 | 0.097 |
| Independent | 0.000 | 6 | 100.00 | 0.000 | 100.00 | 18.00 |
| Independent | 0.500 | 6 | 100.00 | 0.000 | 99.67 | 10.57 |
| Coordinated | 0.000 | 6 | 98.17 | 3.41 | 77.67 | 1476.80 |
| Coordinated | 0.500 | 6 | 99.33 | 1.27 | 57.00 | 748.68 |

95% Student-t descriptive intervals across six heterogeneous development instances, not seed-level or population uncertainty. Only DoD 0 and .5 were tested.


![static dynamic service](figures/dynamicity/static_dynamic_service.png)

[Conditioned static/dynamic table](tables/markdown/static_dynamic.md). Only two DoD levels are measured.

## Coordination Analysis

Full paired differences and eligibility are in [paired methods](tables/markdown/paired_methods.md).

![coordination differences](figures/main/coordination_differences.png)

## MPC Horizon Analysis

![horizon tradeoff](figures/ablations/horizon_tradeoff.png)

## MCTS-Budget Analysis

The quality-only rule chose96 through its reference tie-break and conditioned distance test. That outcome fails the practical runtime/fleet gate. Budget32 achieved similar service with substantially lower runtime; it is a candidate for further bounded algorithm diagnosis, not a validated paper setting.

| Factor | Value | n | Service_pct | Service_CI_half | EVs | Mean_actual_simulations_per_search | p95_epoch_s | Latency_CI_half | Planning_s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Horizon | 1 | 6 | 99.50 | 1.29 | 94.00 | 96.00 | 0.106 | 0.140 | 7.74 |
| Horizon | 3 | 6 | 98.67 | 2.27 | 66.00 | 96.00 | 3.46 | 2.90 | 593.51 |
| Horizon | 5 | 6 | 99.33 | 1.27 | 57.00 | 96.00 | 5.11 | 2.37 | 748.68 |
| Budget | 32 | 6 | 98.83 | 2.52 | 51.17 | 32.14 | 1.39 | 0.934 | 224.94 |
| Budget | 64 | 6 | 99.00 | 1.76 | 55.00 | 64.00 | 2.90 | 1.95 | 444.79 |
| Budget | 96 | 6 | 99.33 | 1.27 | 57.00 | 96.00 | 5.11 | 2.37 | 748.68 |

Only horizon and MCTS-budget factors measured in V2. Top-L remains3 and charging is partial; no evidence for their comparative superiority is claimed.


![budget tradeoff](figures/ablations/budget_tradeoff.png)

## Top-L and Partial-vs-Full Charging

Not rerun in V2. L=3 and partial charging were held fixed. Archived V1 ablations remain diagnostic only. No empty comparison plot or unsupported charging-improvement claim is produced.

## Realtime/Computational Performance

| algorithm | DoD | Runs | Mean_run_planning_s | Mean_epoch_s | Mean_run_p95_s | Max_epoch_s | Mean_simulations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Coordinated | 0.000 | 6 | 1476.80 | 0.259 | 0.665 | 2.28 | 668704.00 |
| Coordinated | 0.500 | 6 | 748.68 | 0.960 | 5.11 | 13.78 | 367744.00 |
| Greedy | 0.000 | 6 | 0.062 | 0.000 | 0.002 | 0.004 | 0.000 |
| Greedy | 0.500 | 6 | 0.097 | 0.000 | 0.001 | 0.006 | 0.000 |
| Independent | 0.000 | 6 | 18.00 | 0.110 | 0.393 | 3.14 | 17808.00 |
| Independent | 0.500 | 6 | 10.57 | 0.041 | 0.127 | 0.495 | 20240.00 |

All online measurements are concurrent diagnostics, outer workers only, BLAS threads1. Mean run p95 is not a pooled p95. Observer/audit/serialization time is excluded from planning time. No V2 realtime experiment was run.


V2 wall-clock experiments are deferred. Mandatory root coverage can exceed a nominal deadline; a dedicated isolated test is required before any realtime claim.

## Representative Trajectory

Pre-specified c101_21, DoD=.5, Coordinated, seeds0. Complete service does not imply fleet efficiency.

![representative routes](figures/representative/representative_routes.png)

![representative evolution](figures/representative/representative_evolution.png)

## Unserved Customers

| Reason | Customers |
| --- | --- |
| SEARCH_NEVER_SELECTED | 13 |
| CANDIDATE_PRUNED_REPEATEDLY | 2 |

Heuristic evidence labels, not exclusive causal proofs. Full per-customer rows retain sampled feasibility, candidate/top-L/intent counts and physical failure types.


[All diagnostic customer-level reasons](all_diagnostic_unserved_customers.csv); [main-grid reasons](unserved_customers.csv). Counts are by sampled customer/run, not independent observations.

## Limitations

These are development diagnostics, not final paper results. Six heterogeneous instances and one seed cannot establish superiority or generalization. A successful service outcome obtained by many reserve routes is not a good fleet/distance solution. Busy-tail coverage is optimistic, not binding; reserve sharing, root coverage and wait semantics change the method. Fixed-versus-flexible is a fleet-policy comparison; V1-versus-V2 is additionally confounded by budget and search changes. Diagnostics sample direct service opportunities and cannot prove every charging-mediated cause of loss. Concurrent timings must not be represented as isolated realtime latency. Main V2 breadth, full charging, L sweeps and repeated seeds remain unmeasured. The full paper campaign is blocked pending review.

## Details

[Per-instance appendix](PER_INSTANCE_RESULTS.md) | [Figure captions](FIGURE_CAPTIONS.md) | [Diagnostic counters](tables/markdown/decision_diagnostics.md) | [Root coverage](tables/markdown/root_coverage.md) | [Raw archive index](raw_index.csv)

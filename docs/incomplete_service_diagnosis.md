# Incomplete-Service Diagnosis



## Status and Oracle

| Question | Answer |
| --- | --- |
| Oracle complete service? | 12/12 complete |
| Coordinated static complete service? | 4/6 complete; mean service 98.17% |
| Flexible fleet improves service? | Mean paired gain 44.50 customers at DoD=.5; mechanism is not a cap-only ablation |
| Extra dynamic vehicles? | Mean 45.67 beyond K_ref |
| Coordination improves service? | Mean coordinated-minus-independent unserved 1.25 across12 paired controls; inspect family rows |
| Root actions evaluated? | Coverage min 1.000; minimum root visits 1 |
| V2 full campaign authorized? | NO. Scientific review required; executor blocked. |


All12 offline reference replays serve100/100 and return safely. Reference and scenario generation were not changed. Oracle routes are never policy inputs or online comparison rows.

## V1 Evidence

| Algorithm | DoD_target | Service_pct | Runs |
| --- | --- | --- | --- |
| Coordinated | 0.000 | 49.83 | 6 |
| Coordinated | 0.500 | 56.50 | 6 |
| Greedy | 0.000 | 47.50 | 6 |
| Greedy | 0.500 | 58.50 | 6 |
| Independent | 0.000 | 52.67 | 6 |
| Independent | 0.500 | 50.83 | 6 |
| MPC-MCTS-H1 | 0.000 | 26.67 | 6 |
| MPC-MCTS-H1 | 0.500 | 38.00 | 6 |

V1 all704 runs had incomplete service, including DoD0. A passing physical audit establishes legality, not global routing quality. Original source commit51a2559 and byte-verified paper_v1_fixed_fleet archive preserve that evidence.

## Fleet Treatment

| Instance | K_ref | V1_served | V2_hard_served | V2_reserve_served | Hard_EVs | Reserve_EVs | Extra_EVs | Hard_distance | Reserve_distance | Hard_planning_s | Reserve_planning_s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c101_21 | 13 | 67 | 67 | 100 | 13 | 58 | 45 | 1695.39 | 4214.56 | 27.07 | 568.49 |
| c201_21 | 5 | 40 | 28 | 100 | 5 | 55 | 50 | 410.41 | 3831.72 | 10.09 | 2517.06 |
| r101_21 | 20 | 64 | 66 | 99 | 20 | 75 | 55 | 1593.67 | 3851.40 | 22.66 | 160.25 |
| r201_21 | 4 | 48 | 47 | 100 | 4 | 44 | 40 | 848.77 | 3052.64 | 20.83 | 517.54 |
| rc101_21 | 21 | 78 | 79 | 97 | 21 | 65 | 44 | 2118.71 | 4721.95 | 23.76 | 131.02 |
| rc201_21 | 5 | 42 | 42 | 100 | 5 | 45 | 40 | 1203.30 | 4453.88 | 11.68 | 597.69 |

Same scenarios/seeds. V2 hard/flexible runs share the selected budget and coverage/wait rules; flexible treatment also changes reserve proposal sharing and busy-tail coverage, so it is a fleet-policy comparison, not a cap-only causal estimate. V1 uses budget16 and different search/wait rules; its column is descriptive provenance only.


The hard cap is a restrictive modeling assumption, but improved flexible service must be read alongside the larger activated fleet. V1/V2 changes are not individually randomized causal ablations. The V2 fixed control shares root-coverage/budget/wait settings, but the flexible mechanism also changes depot proposal sharing and busy-intent coverage.

## Root Exploration

Selected common nominal budget: 96. Candidates are bounded before search. Every admissible root action receives a rollout before UCT revisits; actual simulations are max(nominal, root action count). Coverage of the pruned root set is not coverage of all physically feasible customers. Calibration details: [budget table](../results/paper_v2/tables/markdown/ablations.md).

## Visible Set, Pruning and Wait/Return

| algorithm | DoD | mean_visible_customers | mean_raw_feasible_customers | mean_shortlisted_customers | fraction_feasible_pruned | root_action_coverage | premature_returns | long_waits_with_feasible_work | wait_selections | return_selections | finished_while_known_customers_remain | customers_losing_sampled_feasibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Coordinated | 0.000 | 23.69 | 21.31 | 10.34 | 0.511 | 1.00 | 12.33 | 0.000 | 6078.17 | 77.67 | 43.50 | 1.83 |
| Coordinated | 0.500 | 18.09 | 17.16 | 10.20 | 0.393 | 1.00 | 17.17 | 0.000 | 3480.67 | 57.00 | 39.17 | 0.667 |
| Greedy | 0.000 | 3.89 | 3.83 | 0.823 | 0.784 | NA | 0.000 | 0.000 | 0.167 | 99.83 | 2.00 | 0.000 |
| Greedy | 0.500 | 0.830 | 0.717 | 0.400 | 0.441 | NA | 0.000 | 0.000 | 0.333 | 98.83 | 1.17 | 0.000 |
| Independent | 0.000 | 9.24 | 8.52 | 3.06 | 0.643 | 1.00 | 0.000 | 0.000 | 0.833 | 100.00 | 1.00 | 0.000 |
| Independent | 0.500 | 1.71 | 1.59 | 1.25 | 0.249 | 1.00 | 0.000 | 0.000 | 0.167 | 99.67 | 4.33 | 0.000 |

## Cumulative WAIT Failure

| Instance | Algorithm | DoD | Idle_spells | Long_spells | Long_spells_with_feasible_work | Longest_idle | Wait_selections | Total_planning_s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c101_21 | COORDINATED_MPC_MCTS | 0.500 | 87 | 82 | 77 | 920.32 | 3434 | 568.49 |
| c201_21 | COORDINATED_MPC_MCTS | 0.500 | 94 | 92 | 92 | 3161.76 | 11407 | 2517.06 |
| r101_21 | COORDINATED_MPC_MCTS | 0.500 | 81 | 68 | 67 | 165.47 | 1048 | 160.25 |
| r201_21 | COORDINATED_MPC_MCTS | 0.500 | 83 | 80 | 80 | 767.04 | 2204 | 517.54 |
| rc101_21 | COORDINATED_MPC_MCTS | 0.500 | 74 | 61 | 59 | 130.03 | 593 | 131.02 |
| rc201_21 | COORDINATED_MPC_MCTS | 0.500 | 89 | 84 | 84 | 797.99 | 2198 | 597.69 |
| c101_21 | COORDINATED_MPC_MCTS | 0.000 | 77 | 77 | 72 | 1060.00 | 4636 | 709.67 |
| c201_21 | COORDINATED_MPC_MCTS | 0.000 | 144 | 140 | 140 | 3150.00 | 23943 | 6097.92 |
| r101_21 | COORDINATED_MPC_MCTS | 0.000 | 81 | 74 | 71 | 160.00 | 653 | 145.37 |
| r201_21 | COORDINATED_MPC_MCTS | 0.000 | 76 | 72 | 72 | 890.00 | 3189 | 1081.78 |
| rc101_21 | COORDINATED_MPC_MCTS | 0.000 | 75 | 67 | 66 | 170.00 | 593 | 135.37 |
| rc201_21 | COORDINATED_MPC_MCTS | 0.000 | 77 | 77 | 76 | 860.00 | 3455 | 690.69 |

The per-action long-WAIT counter is zero because individual waits are bounded at10. This does NOT mean active idling is fixed: the physical trace audit above concatenates consecutive waits and exposes long spells while direct feasible work existed at their start. In static c201_21, 23,943 WAIT selections include140 long feasible-work spells; maximum cumulative idle is3150 simulation units. The run spent6097.92s planning. This is an unresolved algorithmic defect, not a successful performance result.

Counters are per-run means followed by equal-instance averaging, not pooled customer-independent observations. Root coverage is not applicable to Greedy. Raw feasibility tests direct authoritative next-service actions for ready EVs plus one reserve template; it excludes exhaustive charging repairs. Last feasible times and cause categories are sampled diagnostic evidence only.

Coordinated mean static service: 98.17%; dynamic: 99.33%. Compare paired rows rather than interpreting this two-level development sample as a general dynamicity effect.

The visible-set and pruning counters test the proposed branching explanation, but do not prove pruning was the unique V1 cause. No nearest-only ranking or full-candidate counterfactual was silently substituted. Full root coverage removes one identified exploration defect; finite-horizon coverage and overlapping predicted tails remain optimistic.

## Algorithm Weakness Found During Development

A naive lazy reserve attained100/100 on the first c101_21 controls by activating100 vehicles. This was rejected as a satisfactory routing result. Adding busy predicted tails to coordinated union coverage reduced redundant immediate departures but exposed repeated WAIT replanning. The final method wakes idle EVs on new releases or bounded-wait expiry, returns when no known request passes cheap capacity/time checks, and excludes station-cycle-invalid fallbacks from rollout choices. Development probes, including failures, are not pooled with the final diagnostic matrix.

## Coordination and Horizon

| Instance | Family | DoD | Comparison | Delta_unserved | Delta_EV | Delta_distance | Distance_pct | equal_service | equal_EVs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c101_21 | C1 | 0.500 | Coordinated - Independent | 0 | -42.00 | NA | NA | True | False |
| c201_21 | C2 | 0.500 | Coordinated - Independent | 0 | -45.00 | NA | NA | True | False |
| r101_21 | R1 | 0.500 | Coordinated - Independent | 1 | NA | NA | NA | False | False |
| r201_21 | R2 | 0.500 | Coordinated - Independent | 0 | -56.00 | NA | NA | True | False |
| rc101_21 | RC1 | 0.500 | Coordinated - Independent | 3 | NA | NA | NA | False | False |
| rc201_21 | RC2 | 0.500 | Coordinated - Independent | 0 | -55.00 | NA | NA | True | False |
| c101_21 | C1 | 0.000 | Coordinated - Independent | 0 | -24.00 | NA | NA | True | False |
| c201_21 | C2 | 0.000 | Coordinated - Independent | 0 | 0.000 | -151.26 | -2.32 | True | True |
| r101_21 | R1 | 0.000 | Coordinated - Independent | 8 | NA | NA | NA | False | False |
| r201_21 | R2 | 0.000 | Coordinated - Independent | 0 | -33.00 | NA | NA | True | False |
| rc101_21 | RC1 | 0.000 | Coordinated - Independent | 3 | NA | NA | NA | False | False |
| rc201_21 | RC2 | 0.000 | Coordinated - Independent | 0 | -30.00 | NA | NA | True | False |

| horizon | service | EVs | planning_s |
| --- | --- | --- | --- |
| 1 | 0.995 | 94.00 | 7.74 |
| 3 | 0.987 | 66.00 | 593.51 |
| 5 | 0.993 | 57.00 | 748.68 |

No significance claim. Coordination differences include the explicit treatment of busy predicted tails; independent control remains local. Hp1 uses the same coordinated fleet manager as Hp3/5 so this is a horizon-only diagnostic, not a separate independently designed baseline.

## Every Final Unserved Customer

| Reason | Customers |
| --- | --- |
| SEARCH_NEVER_SELECTED | 13 |
| CANDIDATE_PRUNED_REPEATEDLY | 2 |

Heuristic evidence labels, not exclusive causal proofs. Full per-customer rows retain sampled feasibility, candidate/top-L/intent counts and physical failure types.


[Complete per-customer diagnostic table](../results/paper_v2/all_diagnostic_unserved_customers.csv). SEARCH_NEVER_SELECTED denotes a witnessed direct feasible opportunity not converted into service; TIME_WINDOW_EXPIRED is a final condition, not proof that expiry was unavoidable. Charging reachability cannot be certified by a direct-action failure alone.

## Scientific Decision

The full campaign remains blocked regardless of test success. Review static service, extra fleet, waiting and runtime together. Complete service alone, especially using many extra routes, does not demonstrate a strong fleet/distance solver. Remaining work is to validate economical route integration and reserve admission without optimistic-tail deferral, and then repeat a bounded diagnostic comparison before authorizing final breadth.

## Proposed Configuration

No final configuration is accepted. The recorded quality-only rule selected96, but runtime and fleet inflation fail the gate. Keep homogeneous lazy reserve K_max=n, charged root coverage and the exact physical model; use32 as a lower-cost development control when testing future corrections to route integration, overlapping forecasts and repeated idling. Hp5/L3/partial and limits12/4/5 remain diagnostic settings, not a validated final recommendation. Do not rerun the full grid.

## Presentation Scope

Only measured diagnostics receive figures. No one-point DoD plots, no complete-service distance plot for empty strata, no empty Top-L/charging/realtime figures. Main report: [PAPER_RESULTS.md](../results/paper_v2/PAPER_RESULTS.md).

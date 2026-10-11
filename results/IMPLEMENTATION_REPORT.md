# Final-Track Implementation and Screening Report

## Status

Implementation and verification completed; scientific screening **FAIL**.
No final paper-performance or superiority claim is supported.
All 36 Stage-1 conditions completed, all were structurally valid, and 32 were
incomplete in service. Stage 2, main, ablations, and realtime were not executed.
No commit, push, or publication was performed.

The attempted early stop after the first static triplet was not executed because
approval review was unavailable. The already-running Stage-1 process subsequently
completed its bounded 36-run plan. Its gate blocked Stage 2. On resumption, process
inspection found no Python experiment running. This report does not claim the
early stop succeeded.

## Reproducible Identity

- Base Git revision: `38d0d015e5255d1eb4c9d3de61345829f19f379a`; current edits are uncommitted.
- Executed source SHA-256: `90c957c01fac4d8ab091f5a7f83e22cd7eadeca87611f577944010b885ae07d1`.
- Screening configuration SHA-256: `62a7cb859703d4b292887dbb4950214ddd59165af274d8a246e323f975c784d2`.
- Manifest: `results/screening/stage1/manifest.json`; run files under its `runs/` directory.
- Current source/configuration, benchmark/scenario/result hashes, replay audits, and gate decision were reverified after execution.
- Python 3.12.10, Windows 11 AMD64; NumPy 2.5.3, SciPy 1.18.1, pandas 3.0.6, matplotlib 3.11.2, PyYAML 6.0.3.
- CLI sets OMP/OpenBLAS/MKL thread counts to one; no outer or agent parallelism was used for screening.
- Benchmark files are unchanged (`git diff --exit-code -- data/evrptw_instances` passed).

## Deleted Files and Directories

Historical generated outputs were removed from the active tree and remain in Git
history at the base revision. This was a one-time cleanup, not deletion of the new
screening evidence.

- Old trees: `results/archive_preobjective_fix/`, `campaigns/`, `development_route_continuity/`, `figures/`, `paper/`, `paper_v1_fixed_fleet/`, `paper_v2/`, `performance/`, `raw/`, `summaries/`, `tables/`, and `traces/` under `results/`.
- All stale `data/generated_scenarios/` artifacts; only its policy README remains. New scenarios are under `results/scenarios/`.
- Seven stale/nondefault reference caches: `c101C10_30ce470c911dcd27.json`, `c101C5_a3c20e8bb7a230f6.json`, `c101C5_bfc255d96a5d5ba8.json`, `c101_21_4f39f00d2a668f00.json`, `c103C15_bcf5f4561487f7ec.json`, `r104C5_3c21c451299beb06.json`, `rc105C5_83ff54d8ed3b4d89.json`. The remaining 61 reference caches match the default solver configuration, versions, and benchmark hashes.
- Obsolete modules: `evrp/reserve.py`, `evrp/campaign.py`, `evrp/paper.py`.
- Historical configs: `benchmark.yaml`, `calibration.yaml`, `default.yaml`, `paper.yaml`, `paper_v2_proposal.yaml`, `pilot.yaml`, `representative.yaml`.
- Old docs: `implementation_report.md`, `incomplete_service_diagnosis.md`, `performance_analysis.md`, `performance_results.md`, `reserve_fleet_v2.md`, `route_continuity_followup.md`.
- Historical `scripts/` campaign, V2/continuity diagnosis, reporting, calibration, profiling, and performance-verification scripts were removed.
- Obsolete tests: `test_campaign.py`, `test_parallel_campaign.py`, `test_paper.py`, `test_scientific_v2.py`, `test_route_continuity.py`; old policy-specific performance golden fixtures were replaced by current deterministic cached/uncached execution checks. Physics and information-boundary tests remain.

## Modified and New Files

Modified core modules: `analysis.py`, `audit.py`, `baselines.py`, `cli.py`,
`continuity.py`, `coordinator.py`, `diagnostics.py`, `experiments.py`, `mcts.py`,
`mpc.py`, `plotting.py`, `simulator.py`, `storage.py`, and `versions.py` under `evrp/`.

Modified configuration/support: `.gitignore`, `README.md`, `pyproject.toml`,
`configs/{debug,validation,main,ablations,realtime}.yaml`, `results/README.md`,
`docs/{methodology,assumptions}.md`, and
`tests/{test_hierarchy,test_performance,test_planning,test_reporting}.py`.

New files: `evrp/repair.py`, `evrp/studies.py`,
`configs/{screening,smoke}.yaml`,
`docs/{experiment_protocol,reproducibility}.md`,
`data/generated_scenarios/README.md`, and
`tests/{test_final_fleet,test_final_mcts,test_repair,test_studies}.py`.

Generated artifacts are ignored by Git, including this report, manifests, scenarios,
raw results, validation CSV, audit reports, summaries, CSV/LaTeX tables, test XML,
and PNG figures with source CSVs. No generated research output is intentionally
written outside repository-local `results/`.

## Final Architecture

1. Initialize exactly `K_ref` physical EVs. Reference routes never reach online policies.
2. Process releases/completions, update measured states, and replay persistent suffixes.
3. Mask other owners' customers from each EV. Busy actions are immutable.
4. Run finite-horizon MPC-MCTS using existing UCT, caches, candidate pruning, partial charging, and safe-return constraints.
5. Retain quality top-L by default; optional parameter-free coverage diversity is available.
6. Reconcile candidate prefixes with every retained customer obligation. Full suffixes can exceed the local horizon without increasing that search horizon.
7. Select customer-disjoint routes through sequential coverage, activation, and distance MILPs. Independent uses deterministic conflict handling instead.
8. Apply one regret-2 repair phase to uncovered released customers, across the fixed fleet, including unused depot EVs and origins after busy actions.
9. Perform one final replay/reconciliation pass; invalid commitments fail explicitly.
10. Execute first actions and retain suffixes through the last planned service, excluding trailing WAIT/RETURN.

RH_REGRET uses the same persistent ownership, repair, and physics with no MCTS or
MILP. No optional relocate pass was added. GREEDY remains available as a sanity
baseline; H1 and coverage diversity are ablations, not screened main methods.

Repair prioritizes a unique option, then regret-2, slack, due date, and ID. It uses
incremental distance including return, with activation only breaking exact-cost
ties. Charging construction is conservative: bounded station bridges plus a
full-charge connection fallback, without backtracking earlier charge choices.
Construction failure is not proof of physical infeasibility.

## CLI and Output Policy

Implemented commands: `validate`, `smoke`, `run --instance ...`,
`screening --stage 1|2|all`, `main`, `ablations`, `realtime`, `aggregate`, `tables`,
`plot`, and `audit`, all through `python -m evrp.cli`.

Main/ablations/realtime are planning-only by default; `--execute` additionally
requires a fresh, independently reverified screening PASS. Planned counts are
324/108/24 before scenario eligibility filtering. Output paths that escape
repository-local `results/` are rejected. Screening does not auto-launch main.

## Tests and Smoke

- Full suite: **248 passed**. Final machine-readable evidence: `results/verification/pytest.xml`.
- Final test run completed in 24.16 seconds. The later-study execution guard rejected the failed gate as expected.
- Default `git diff --check` reports one trailing blank line at `evrp/experiments.py:359`; it was left untouched to preserve the executed source fingerprint. No algorithm edits were made after screening began.
- Tests cover fixed fleet/activation, ownership, hidden-customer isolation, invalid retained routes, busy actions, insertion order/termination, partial/multihop charging, deterministic MCTS/diversity, horizon, cooperative deadline incumbents, MILP versus exhaustive enumeration, output confinement, gate tampering, and C/R/RC end-to-end replay.
- Smoke: 18/18 runs completed and passed structural audits. Twelve served all 5 customers; six RC runs served 4/5. These are not reported as complete-service successes.
- Three small-instance dynamic conditions could not realize target DoD exactly; smoke discloses this rather than treating those scenarios as eligible main evidence.

## Schneider Reference Validation

All four configured small reference cases passed vehicle matching and published
rounded-distance tolerance. This validates the reference/physics implementation,
not online algorithm completeness or larger-instance optimality.

| Instance | Published EVs | Computed EVs | Published distance | Computed distance |
|---|---:|---:|---:|---:|
| c101C5 | 2 | 2 | 257.75 | 257.747452 |
| c103C5 | 1 | 1 | 176.05 | 176.054433 |
| c206C5 | 1 | 1 | 242.56 | 242.555652 |
| c208C5 | 1 | 1 | 158.48 | 158.480660 |

Evidence: `results/validate/reference_validation.csv`, using the repository's
Schneider Table-3 metadata and its source attribution.

## Stage-1 Results

Six instances, DoD 0/0.5, scenario/algorithm seeds 0, Hp5/Hc1/L3, partial charging,
fixed reference fleet, continuity and regret repair enabled. All target DoDs were
realized. No instances, seeds, fleets, objectives, or settings were changed after
outcomes became available.

Values below are customers served out of 100. All matched algorithms had the
same physical fleet; actual activations are available in the per-run CSV.

| Instance | K_ref | DoD | RH_REGRET | Independent | Coordinated |
|---|---:|---:|---:|---:|---:|
| c101_21 | 13 | 0 | 93 | 87 | 91 |
| c201_21 | 5 | 0 | 100 | 79 | 70 |
| r101_21 | 20 | 0 | 89 | 90 | 91 |
| r201_21 | 4 | 0 | 72 | 68 | 77 |
| rc101_21 | 21 | 0 | 100 | 100 | 100 |
| rc201_21 | 5 | 0 | 92 | 83 | 68 |
| c101_21 | 13 | 0.5 | 81 | 81 | 76 |
| c201_21 | 5 | 0.5 | 93 | 95 | 76 |
| r101_21 | 20 | 0.5 | 84 | 82 | 77 |
| r201_21 | 4 | 0.5 | 76 | 83 | 96 |
| rc101_21 | 21 | 0.5 | 86 | 84 | 83 |
| rc201_21 | 5 | 0.5 | 90 | 89 | 89 |

| Method | Static complete /6 | Dynamic complete /6 | Dynamic mean service |
|---|---:|---:|---:|
| RH_REGRET | 2 | 0 | 85.00% |
| Independent | 1 | 0 | 85.67% |
| Coordinated | 1 | 0 | 82.83% |

Coordinated fails all three predeclared feasibility criteria: static 6/6 complete,
dynamic mean >=98%, dynamic >=5/6 complete. All 36 runs returned safely with zero
recorded time-window, battery, capacity, duplicate-service, or information-boundary
violations; independent replay audits also passed. Physical validity is not
complete service.

### Budget Discrepancy

Nominal iterations were 32, but the pre-existing root-coverage rule, explicitly
enabled in the frozen configuration, uses `max(32, root_action_count)`. Of 6,968
MCTS searches, 94 used more than 32; the maximum was 34. Thus this is **not a strict
32-simulation screen**. This is an explicit remaining protocol discrepancy, not an
outcome-driven budget increase. No post-result retuning or replacement run was
performed. Future execution needs a decision on strict 32 versus root coverage;
the present failure cannot authorize the next stage under either interpretation.

### Matched Comparisons

At DoD .5, coordinated versus RH_REGRET has service wins/ties/losses 1/0/5; versus
independent, 1/1/4. Mean unserved differences are +2.167 and +2.833 respectively.
Full paired mean/median/bootstrap-CI tables, with conditional EV/distance rows,
are in `results/screening/GATE.md`. They are Stage-1 diagnostics, not Stage-2 results.
No vehicle/distance superiority is inferred from unequal service counts.

## Runtime and Diagnosis

| Method | Total event-planning seconds, 12 runs | Repair seconds | Largest run-level p95 (s) |
|---|---:|---:|---:|
| RH_REGRET | 1590.68 | 1587.82 | 4.662 |
| Independent | 2091.55 | 2013.17 | 7.744 |
| Coordinated | 2371.36 | 2290.77 | 10.344 |

Coordinated's largest single event took 126.10 seconds. Timing includes local
planning, selection, repair, and final reconciliation, but not offline reference
generation or observer-only diagnostics. These are iteration-screen timings,
not isolated realtime-study results. Root generation and other individual calls
are non-preemptible; wall-clock MCTS deadlines remain cooperative, not hard realtime.

Evidence and limits:

- Ownership and physics replay passed; no evidence of silently dropped retained customers or fleet expansion was found.
- Every generated MCTS root action was visited. This does not mean every physically feasible customer or route was generated.
- Repair dominates measured time. Enumerating positions and replaying full routes is expensive, especially in the small-fleet, long-route cases.
- Static c201 and rc201 service is much worse with MCTS than RH_REGRET. Early local-route choices and irrevocable ownership may restrict later insertion; this is a hypothesis requiring controlled diagnosis, not a proven cause.
- Local Hp5 and finite pruned proposals can miss globally compatible route structures. Full-suffix preservation does not remove local-search horizon bias.
- The conservative charging constructor may reject insertions that another charging schedule could make feasible; this is not certified by current diagnostics.
- Root-pruning counters compare raw direct-next-service opportunities with local roots and do not fully account for ownership masks or charging-mediated opportunities. They are not causal pruning-loss counts.
- RH_REGRET has no MCTS roots. Its inherited diagnostic labels such as `CANDIDATE_PRUNED_REPEATEDLY` are not applicable to that baseline and are not interpreted as evidence against it. Likewise `FLEET_CAP_REACHED` is sampled evidence, not proof that a larger fleet is necessary.

## Gate, Blockers, and Unexecuted Studies

**GATE = FAIL.** Stage 2 was not run, so there are no 108-run Stage-2 results.
Main (324 planned), ablations (108 planned), realtime (24 planned), diverse-policy
screening, optional GREEDY screening, and optional relocate experiments remain
unexecuted. Their counts are plans, not completed results.

The blockers are inadequate fixed-fleet service, unfavorable dynamic comparisons,
slow insertion, the nominal-versus-strict iteration discrepancy, and limited causal
diagnostics. Do not increase fleet/budget or silently alter seeds, instances, or
objectives to obtain a favorable result. Any future algorithm change needs a new
explicit protocol and provenance-bound screen; this failed evidence must remain.

## Artifacts

- Gate: `results/screening/GATE.json` and `GATE.md`.
- Audited per-run rows and aggregate notes: `results/screening/stage1/summaries/`.
- CSV/LaTeX table pairs: `results/screening/stage1/tables/`.
- 15 measured diagnostic PNG figures (300 dpi) and exact source CSVs: `results/screening/stage1/figures/`. No final-paper figures are claimed.
- Validation: `results/validate/`; smoke and replay audit: `results/smoke/`.
- Test report: `results/verification/pytest.xml`.

Generic summary/plot intervals use descriptive Student-t intervals. The explicitly
labeled paired gate appendix uses percentile bootstrap intervals. They must not be
confused or presented as independent evidence from additional experiments.

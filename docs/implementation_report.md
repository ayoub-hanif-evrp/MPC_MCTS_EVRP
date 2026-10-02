# Implementation Audit (2026-10-02)

## Status

The task is **not yet complete**. A fundamental objective choice is pending.
The requested distance-only cost, together with a free Wait fallback, causes the
coordinator to select all-Wait solutions. Tests and end-to-end smoke records prove
the issue. Adding a service requirement changes the stated mathematical selection
problem; a service-first lexicographic alternative has been proposed to the user
but has not been substituted without their answer.

## Implemented Files and Architecture

- `evrp/instance.py`, `model.py`: verified Schneider parser and common physical engine.
- `evrp/reference.py`, `scenario.py`: heuristic references, fleet size, reproducible releases.
- `evrp/observation.py`: simulator-private global partition and filtered observation boundary.
- `evrp/mpc.py`, `mcts.py`, `agent.py`: explicit MPC formulation/controller, UCT optimizer, EV agents.
- `evrp/coordinator.py`, `baselines.py`, `simulator.py`: assignment, baselines, non-preemptive events.
- `evrp/experiments.py`, `analysis.py`, `plotting.py`, `cli.py`, `storage.py`: file-based runs, auditing, statistics, figures, protected artifact storage.
- `configs/`: debug, default, full benchmark, one-factor ablations, wall-clock experiments.
- `tests/`: physical, reference/scenario, information boundary, planning, simulator, experiment, regression tests.
- `docs/`, `README.md`, `requirements.txt`, `pyproject.toml`, `.gitignore`: methodology, assumptions, installation, reproducibility.
- `data/reference_schedules/`, `data/generated_scenarios/`: generated artifacts, separate from originals.

Hierarchy: EVAgent owns MPCController, which builds MPCPlanningProblem and calls
MCTSOptimizer.solve. Proposals pass to the assignment coordinator, then only their
first action is dispatched by EventDrivenSimulator. Service horizon and one-action
control horizon are separate. Tail overlap is permitted; duplicate first-action
customer commitment is prohibited.

## Verified Data and Assumptions

Actual fields are `StringID Type x y demand ReadyTime DueDate ServiceTime`, with
vehicle parameters `Q C r g v`. All 92 instances parse. The original benchmark
directory has no git diff. Tests also compare SHA-256 values around operations.
No original file was edited and no alternate dataset was downloaded.

The model uses one tour per EV, uniform station hours/rate, hard service-start
windows, full-precision distances with a 1e-8 feasibility tolerance, and a fixed
fleet from a heuristic reference. Dynamic uniform releases, discrete partial-charge
targets, candidate pruning, service-count horizons, and terminal safe return are
explicit experimental assumptions, detailed in `assumptions.md`.

## Reference Solver

Multi-start time-window-aware feasible insertion, full-charge station repair,
and feasible relocate improvement use the common physical model. Selection is
lexicographic by fewer routes then shorter distance. It is not claimed optimal.
The selected one-start `c101_21` reference has 16 routes and distance
1796.0462117634954. The development construction took approximately 50 seconds.
All requested smoke instances received feasible references; none failed reference
construction. The entire benchmark reference grid was not executed.

## Verification

Latest complete test invocation: `python -m pytest -q`: **76 passed**.
Coverage includes all-instance parsing, missing-parameter rejection, time/energy/load
physics, partial/full charge, multi-station return, scenario preservation, exact
release visibility, hidden-state perturbation, MCTS/terminal information isolation,
distinct proposals, customer-count horizons, UCT, root statistics, commitment/tail
separation, exhaustive assignment comparisons, non-preemption during customer-window
waiting, simultaneous events, fixed-seed replay, process-parallel equivalence,
reference persistence, failed-run retention, and trace tampering detection.
End-to-end GREEDY tests separately verify full-charge targets and actual partial
charges. Independent C5 release scenarios have been persisted for seeds 0, 1, 2.

A near-simultaneous event exposed rejection of a positive wait below 1e-8; this was
fixed and given a regression test. Full-charge SOC assignment was also corrected
to land exactly at the requested target rather than accumulate rounding overshoot.

## Smoke Results

All seven requested coordinated MPC-MCTS smoke cases ran end-to-end, including the
100-customer case with two iterations and H_p=1. Under the literal current objective,
they served zero customers and were correctly recorded as infeasible. Their
zero distance is not a routing success. Safe returns and physical invariants held.

Greedy smoke runs exercised actual routing and charging:

| Instance | Target DoD | Served | Total distance | All served? |
| --- | ---: | ---: | ---: | --- |
| c101C5 | 0.00 | 4/5 | 253.011 | No |
| c101C5 | 0.50 | 5/5 | 341.664 | Yes |
| r104C5 | 0.50 | 5/5 | 195.416 | Yes |
| rc105C5 | 0.50 | 4/5 | 183.222 | No |
| c101C10 | 0.50 | 9/10 | 482.769 | No |
| c103C15 | 0.50 | 13/15 | 447.706 | No |
| c101_21 | 0.50 | 65/100 | 1716.532 | No |

All seven greedy runs returned every EV safely, with zero battery/capacity/window
violations, no duplicate service, and no trace-audit failures. Unserved requests
remain in results. These low-budget/single-seed checks are not comparative evidence.
Actual realized DoD is stored and can differ from the target because zero-bound
customers cannot be dynamic and exact counts use half-up rounding.

Greedy verification records are under `results/verified_greedy/`; development
coordinated records are under `results/smoke/`. Aggregation ran successfully and
36 matplotlib figures were created under `results/figures_greedy/`; an SOC plot was
visually inspected. Runtime values vary across machines/runs.

## Commands

```powershell
python -m pytest -q
python -m evrp.cli scenario --instance c101C5 --config configs/debug.yaml
python -m evrp.cli run --instance c101C5 --config configs/debug.yaml --algorithm GREEDY
python -m evrp.cli run --instance c101C5 --config configs/default.yaml --algorithm COORDINATED_MPC_MCTS
python -m evrp.cli benchmark --config configs/benchmark.yaml
python -m evrp.cli ablations --config configs/ablations.yaml
python -m evrp.cli benchmark --config configs/realtime.yaml
python -m evrp.cli aggregate --input results/verified_greedy --output results/aggregate_greedy
python -m evrp.cli plot --input results/verified_greedy --output results/figures_greedy
```

No commit or push was made. The active project goal remains open. Resolve the
service requirement, update MPC/MCTS/coordination consistently, rerun all baselines
and ablations needed for correctness, and refresh this audit before claiming the
proposed method or the project is complete.

# Persistent-Route Coordinated Multi-Agent MPC-MCTS for Dynamic EVRPTW

**Status: implementation and screening stage. No final paper-performance claim yet.**

This training-free research implementation asks whether persistent route coordination
between independently planned EVs improves dynamic EVRPTW performance over independent
MPC-MCTS and rolling-horizon regret insertion. Local Schneider benchmark files are
immutable. Historical V1/V2 outputs are preserved at Git commit `38d0d01`; they are
not evidence for the current method.

## Method

```text
Released requests and measured EV states
  -> replay retained executable routes and preserve feasible ownership
  -> finite-horizon MPC subproblems solved approximately by MCTS
  -> top-L feasible route candidates
  -> sequential MILP fleet coordination
  -> regret-2 repair of uncovered released requests
  -> one final validation/reconciliation pass
  -> execute first actions, retain executable suffixes, replan after feedback
```

Every matched algorithm has exactly `K_ref` physical EVs (`fleet_mode:
fixed_reference`). Only the reference fleet size reaches online policies; reference
routes and unreleased requests do not. Unused depot EVs count as activated only
after departure. No vehicles are created beyond `K_ref`.

Each committed customer has at most one owner. An EV sees released unassigned
customers and its own commitments, excluding customers owned by others. The finite
prediction horizon bounds new MCTS search. Retained executable suffixes, including
repaired commitments, may be longer and must remain feasible under replay.
Terminal WAIT/RETURN after the last service are not retained as commitments.
Temporary idleness must not force premature return: an active EV can wait while
latest-safe-return slack remains.

The fleet objective is lexicographic: minimize unserved customers, then activated
vehicles, then distance. Coordination selects customer-disjoint executable routes;
regret-2 repair follows coordination and precedes dispatch.

Main algorithms are `GREEDY`, `RH_REGRET`, `INDEPENDENT_MPC_MCTS`, and
`COORDINATED_MPC_MCTS`. `MPC_MCTS_H1` is an ablation. Coverage-diverse top-L selection
is optional and enters the main study only if screening supports it.

## Setup and CLI

Python 3.11+ is required. From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m evrp.cli --help
```

The implemented CLI is:

```powershell
python -m evrp.cli validate
python -m evrp.cli smoke
python -m evrp.cli run --instance c101C5
python -m evrp.cli screening
python -m evrp.cli aggregate
python -m evrp.cli tables
python -m evrp.cli plot
python -m evrp.cli audit
```

Later studies require explicit execution and the applicable gates:

```powershell
python -m evrp.cli main --execute
python -m evrp.cli ablations --execute
python -m evrp.cli realtime --execute
```

Never launch the main study automatically. All generated research artifacts,
including scenarios, belong under repository-local `results/`. Output overrides
must not escape that directory.

## Screening Before Claims

Stage 1 uses `c101_21`, `c201_21`, `r101_21`, `r201_21`, `rc101_21`, and `rc201_21`,
at DoD `0.0/0.5`, scenario/algorithm seeds `0`, and 32 MCTS simulations. Use horizon
5, control horizon 1, top-L 3, partial charging, fixed `K_ref`, continuity, and
regret repair. Compare RH_REGRET, independent MPC-MCTS, and coordinated MPC-MCTS.
Stop and diagnose poor static service before launching further experiments.

Stage 2 is conditional on Stage 1 passing: the same six instances, DoD
`0.25/0.50/0.75`, scenario seeds `0/1`, and the same three methods (108 runs).
Write evidence and the gate decision to `results/screening/GATE.md`. Compare service
first, vehicles only at equal service, and distance only at equal service and
vehicle count. Failed screening blocks the main campaign.

## Documentation

- [Methodology](docs/methodology.md): ownership, search, coordination, and repair.
- [Assumptions](docs/assumptions.md): physics, information, and limitations.
- [Experiment protocol](docs/experiment_protocol.md): study design and gates.
- [Reproducibility](docs/reproducibility.md): provenance, validation, and execution.
- [Output policy](results/README.md): generated artifacts and Git exclusions.

No new validation, screening, or superiority result is asserted by this README.
Current local evidence is recorded in `results/IMPLEMENTATION_REPORT.md` and
`results/screening/GATE.md`; generated evidence is intentionally not committed.

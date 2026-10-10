# Reproducibility

Status: implementation and screening. These are execution and evidence requirements
for the implemented fixed-fleet track.

## Environment and CLI

Use Python 3.11+ from the repository root. Install `requirements.txt` and record
actual Python/package/MILP versions; minimum dependency bounds alone do not specify
a reproducible environment.

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

Check individual command help in the working revision. Configuration roles under
`configs/` are `debug.yaml`, `validation.yaml`, `smoke.yaml`, `screening.yaml`,
`main.yaml`, `ablations.yaml`, and `realtime.yaml`.

For Stage-1 reporting, use its explicit input and study name:

```powershell
python -m evrp.cli aggregate --input results/screening/stage1/runs --output results/screening/stage1/summaries
python -m evrp.cli tables --input results/screening/stage1/summaries --output results/screening/stage1/tables
python -m evrp.cli plot --input results/screening/stage1/summaries --output results/screening/stage1/figures --study screening_stage1
```

Generic aggregate CIs are descriptive Student-t intervals; the screening gate uses
paired bootstrap intervals. Plots omit unexecuted studies and empty measurement
panels. Screening plots are 300-dpi PNG with exact source CSV companions.

After validation and applicable gates, later studies require explicit execution:

```powershell
python -m evrp.cli main --execute
python -m evrp.cli ablations --execute
python -m evrp.cli realtime --execute
```

Never automatically execute main, commit outputs, push, or publish. Follow the
[experiment protocol](experiment_protocol.md) for study order and gates.

## Inputs and Provenance

Benchmark files under `data/evrptw_instances/` are immutable. Reuse existing
reference schedules only when benchmark hash, solver version, and configuration
match. Stale references must not silently establish `K_ref`. Reference routes
stay offline; only fleet size reaches policies.

Generate each scenario once and share it across matched algorithms. Bind it to
benchmark/reference identities, generator version, target/realized DoD, selection
mode, and scenario seed. Unattainable main-study dynamic counts are ineligible.
Do not regenerate a favorable scenario for a particular algorithm.

Record effective configuration, Git revision and source-content identity including
dirty-tree changes, dependency hashes, objective/schema versions, both seeds,
timestamps, packages, hardware, and execution mode. Preserve replayable actions,
ownership evidence, search/repair diagnostics, runtime, failures, and audit status.
Changed source/configuration identities must not overwrite the same experiment.

## Output and Determinism

All new research artifacts must resolve inside repository-local `results/`:
scenarios, raw runs, reports, plots, tables, and profiling records. Do not use home,
`%LOCALAPPDATA%`, external scratch paths, or overrides that escape that root.
`data/generated_scenarios/` is a retired cache, empty except for its README.
Existing reference schedules are inputs, not permission to create new outputs
outside `results/`.

Fixed-iteration runs use controlled seed derivation and deterministic ordering.
Logical repeatability requires matching inputs and dependencies; latency and
deadline-limited search are not bitwise reproducible. Keep realtime runs isolated,
record worker/thread settings, and separate local search budgets from full event
planning time including coordination and repair.

Git ignores generated results except the policy README and optional `.gitkeep`
placeholders. See [output policy](../results/README.md). Preserve new Stage-1 outputs:
historical cleanup is a one-time operation, not a step to repeat before execution.

## Evidence Requirements

- Report tests actually executed and their outcomes, including physics, information
  boundaries, ownership, fixed fleet, regret ordering, local horizons, MILP checks,
  and end-to-end replay.
- Report current Schneider reference validation separately from online service.
  Historical statements do not substitute for a current validation run.
- Audit disk records before aggregation. Disclose failed, incomplete, invalid,
  missing, and ineligible conditions.
- Report Stage 1, Stage 2 only if Stage 1 passed, and evidence behind
  `results/screening/GATE.md`. Missing evidence is never PASS.
- Follow the protocol's service/vehicle/distance conditioning and record bootstrap
  provenance.
- List remaining scientific blockers and studies not executed. Implementation
  progress and old V1/V2 results do not establish final paper-performance claims.

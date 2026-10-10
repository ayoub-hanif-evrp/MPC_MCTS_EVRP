# Results and Output Policy

Status: implementation and screening. No final paper-performance claim yet.

All newly generated research artifacts stay inside repository-local `results/`:
scenarios, raw records, traces, validation, screening, aggregates, tables, figures,
and timing reports. Home-directory, `%LOCALAPPDATA%`, and other external output
paths are not permitted.

Git ignores generated contents. Only this README and optional `.gitkeep` directory
placeholders are eligible for tracking. Do not force-add generated reports/data.
Separate studies and source/configuration identities; do not overwrite changed runs.

Stage 1 precedes Stage 2. Record screening evidence and the gate decision in
`results/screening/GATE.md`; this generated report remains ignored. Missing evidence
is not PASS. Main requires the applicable passing gate and explicit execution and
must never launch automatically.

Historical V1/V2 outputs were removed and remain preserved at Git commit `38d0d01`.
Do not include them in current aggregates or claims. Cleanup is not a recurring
policy: preserve newly generated Stage-1 and later outputs, even when directory
names match historical output names.

See [experiment protocol](../docs/experiment_protocol.md) and
[reproducibility](../docs/reproducibility.md).

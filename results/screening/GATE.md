# Screening Gate

GATE = FAIL

Differences are coordinated minus baseline; negative is better.
EV comparisons require equal service; distance requires equal service and EVs.
Intervals are deterministic percentile paired-bootstrap CIs for mean differences.
Stage 1: coordinated static 6/6 complete, dynamic mean >=98%, dynamic >=5/6 complete.

## stage1

Status: FAIL

- Coordinated dynamic mean service is below 98%
- Coordinated dynamic service must be complete on at least five instances
- Coordinated static service must be complete on all six instances

| Algorithm | Static complete /6 | Dynamic complete /6 | Dynamic mean service |
|---|---:|---:|---:|
| RH_REGRET | 2 | 0 | 0.850 |
| INDEPENDENT_MPC_MCTS | 1 | 0 | 0.857 |
| COORDINATED_MPC_MCTS | 1 | 0 | 0.828 |
## stage2

Status: NOT RUN


## Eligibility

Ineligible scenarios remain in manifests and are excluded from Stage 2.


No main, ablation, or realtime study is launched by screening.

## Verified Stage-1 Evidence

All 36 planned runs completed and passed disk-record replay audits. There were
32 incomplete-service runs, no technical failures, and no structural failures.
All 12 scenario conditions achieved their target DoD. Seeds were both zero.
Source identity: `90c957c01fac4d8ab091f5a7f83e22cd7eadeca87611f577944010b885ae07d1`.
Full evidence and limitations: `results/IMPLEMENTATION_REPORT.md`.

### Paired Stage-1 Diagnostics (Not Stage 2)

These additional descriptive comparisons do not replace the failed feasibility
criterion. Differences are coordinated minus baseline. Negative is better.
EVs require equal served counts; distance also requires equal EV counts.
Bootstrap: 2,000 percentile resamples, seed 0, matched instance/scenario pair as
resampling unit, separately by DoD. A CI is undefined for fewer than two pairs.

| DoD | Baseline | Metric | n | Wins | Ties | Losses | Mean | Median | 95% bootstrap CI |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 0 | RH_REGRET | Unserved | 6 | 2 | 1 | 3 | 8.167 | 1.000 | [-1.833, 19.337] |
| 0 | RH_REGRET | EVs | 1 | 0 | 0 | 1 | 1.000 | 1.000 | undefined |
| 0 | RH_REGRET | Distance | 0 | 0 | 0 | 0 | undefined | undefined | undefined |
| 0 | Independent | Unserved | 6 | 3 | 1 | 2 | 1.667 | -0.500 | [-4.500, 8.500] |
| 0 | Independent | EVs | 1 | 0 | 1 | 0 | 0.000 | 0.000 | undefined |
| 0 | Independent | Distance | 1 | 0 | 0 | 1 | 145.511 | 145.511 | undefined |
| 0.5 | RH_REGRET | Unserved | 6 | 1 | 0 | 5 | 2.167 | 4.000 | [-7.504, 10.333] |
| 0.5 | RH_REGRET | EVs | 0 | 0 | 0 | 0 | undefined | undefined | undefined |
| 0.5 | RH_REGRET | Distance | 0 | 0 | 0 | 0 | undefined | undefined | undefined |
| 0.5 | Independent | Unserved | 6 | 1 | 1 | 4 | 2.833 | 3.000 | [-4.667, 10.667] |
| 0.5 | Independent | EVs | 1 | 0 | 1 | 0 | 0.000 | 0.000 | undefined |
| 0.5 | Independent | Distance | 1 | 1 | 0 | 0 | -79.709 | -79.709 | undefined |

## Budget Disclosure

The configured nominal budget was 32 with root coverage enabled before execution.
That existing rule permits `max(32, root_action_count)` simulations. Observed
maximum: 34; 94 of 6,968 MCTS searches exceeded 32. These data must not be described
as a strict 32-simulation experiment. No budget was changed after seeing outcomes.
This discrepancy needs an explicit protocol decision before future experiments;
it does not rescue the service failure or authorize Stage 2.

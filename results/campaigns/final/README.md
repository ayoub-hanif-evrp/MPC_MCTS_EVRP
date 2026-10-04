# Full Research Campaign

**CANCELLED on 2026-10-03.** The user stopped this design after 58 completed
runs. Do not resume it. The following launch notes are historical only; the old
entry points now reject execution. See `docs/performance_analysis.md` and
`configs/paper.yaml` for the separately gated replacement design.

Launched on 2026-10-03 at the user's request. This is the full configured
experiment, not the earlier six-case smoke test. Check `status.json` for live
state; do not treat partially populated summaries as final results.

| Study | Configured runs |
| --- | ---: |
| Pilot | 40 |
| Ablations | 69 |
| Realtime | 108 |
| Main (56 instances, 5 DoDs, 5 scenario seeds, 3 algorithm seeds, 4 algorithms) | 16800 |
| Total | 17017 |

`manifest.json` freezes configurations and source hash. `status.json` records
current experiment, heartbeat, completed count, failed count and final status.
`parallel_stdout.log` records each completed job; `parallel_stderr.log` records
any fatal error. The original sequential logs remain preserved.
`raw/` retains complete gzip-compressed JSON traces, not reduced sample outputs.

After each study, the runner audits raw records and refreshes `summaries/`,
`tables/`, and `figures/`. Figures are PNG only at 300 dpi, with exact data CSVs;
no PDF figures are generated. Final main and ablation figures are placed in
`figures/main/`, `figures/ablations/`, and `figures/diagnostics/`. Pilot, realtime
and fixed representative figures have separate folders.

The study order is pilot, ablations, realtime, main. On explicit user approval,
the runner was switched to up to four concurrent experiments, limited by available
physical memory. Realtime and parallel-agent comparison runs execute in isolation;
their configured agent-worker counts are unchanged. Concurrent fixed-iteration
timings are NOT isolated latency measurements. Raw requested configs identify the
execution profile and executor hash. `execution.jsonl` records job start/end times;
`summaries/timing_context.csv` makes the distinction explicit alongside tables.

Keep the computer on and awake; no sleep or power settings were changed. The first
two sequential 100-customer cases took approximately 22 and 7 minutes, so the full
grid is a substantial computation workload, potentially weeks rather than hours.
Freeing memory by closing unused applications can permit more workers to run.

The runner automatically finishes reporting after every job has been processed.
`completed_with_failures` explicitly means some execution/integrity checks failed;
incomplete but structurally valid service is separately reported in failure tables.
No statistical superiority or full-service guarantee is implied by completion.

Resume an interrupted campaign from the repository root with:

```powershell
python -m scripts.run_full_campaign --workers 4
```

A process lock prevents duplicate runners. Source changes cause a safe stop to
prevent mixing revisions; use a new `--output` for a deliberately changed experiment.
The free-space guard stops at 10 GiB remaining. The runner does not automatically
commit or push results. Published status, logs, and results are point-in-time
snapshots, not a live progress feed or evidence that the campaign has finished.
The GitHub snapshot published at the user's request includes completed raw
records; later completions require another push. While this campaign is running,
its local checkout stays at the launch commit because Git commit IDs participate
in run identities. Publishing uses a separate snapshot branch without changing
that checkout or the solver source.

The 40 completed pilot records were retained for resume. Two completed sequential
ablation records were preserved under `raw/ablations/archive_isolated_launch/`;
they are excluded from concurrent comparisons and rerun with explicit execution
profiles. The interrupted in-progress case was requeued, not marked completed.
`parallel_manifest.json` records the new executor revision and worker limit.

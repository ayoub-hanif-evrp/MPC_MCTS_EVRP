# Research Outputs

Latest development: [route-continuity follow-up](development_route_continuity/README.md),
two preserved 36-condition grids. This does not replace V1/V2 or authorize a
new full paper campaign.

The old 17,017-job campaign is cancelled with58 completions preserved. The compact
704-condition V1 campaign completed, but every run had incomplete service under
the hard reference-fleet cap. It is diagnostic evidence, not final paper results.
V2 completed only the prescribed six-instance diagnostics (12 offline controls,
66 unique online conditions). Its scientific/runtime gate failed; no full V2
campaign is authorized. Read [the current report](paper_v2/PAPER_RESULTS.md).

```text
results/
  performance/               Profiles, calibration, exactness checks, runtime gate
  campaigns/final/           Cancelled 17,017-job design; 58 completions preserved
  paper/                     Original completed V1 compact-study outputs
  paper_v1_fixed_fleet/       Byte-verified V1 diagnostic snapshot
  paper_v2/                  Bounded diagnostic records, report, tables and figures
  archive_preobjective_fix/   Original development history, excluded by default
  raw/
    validation/              Validation run records
    pilot/                   Small online smoke/pilot JSON records
    main/                    Explicit full benchmark only; not run
    ablations/               One-factor experiments; not run
    realtime/                Wall-clock experiments; not run
  traces/representative/      Fixed qualitative trace, not selected for quality
  summaries/                 Full-precision audited CSVs and audit report
  tables/csv/                Rounded publication tables
  tables/latex/              Landscape tables (rotating, booktabs, graphicx)
  figures/main/              Service-first study-level figures
  figures/ablations/         Empty, explicitly labelled until ablations are run
  figures/diagnostics/       Mean and within-run p95 latency by size and DoD
  figures/representative/    Routes, disclosure/service, SOC, decisions, proposals
```

V1 figures are PNG-only. V2 diagnostic figures follow the revised requirement:
PDF vector, 300-dpi PNG and exact-data CSV. V2 generates no empty figures and keeps
unmeasured studies explicitly separate. The pre-specified representative is
c101_21/DoD.5/Coordinated/seeds0, and the full route figure requires complete service.

Run JSON contains identity, scenario, algorithm, primary, secondary, coordination,
computation, integrity, provenance, and replayable traces. Deterministic identities
include configuration, benchmark/scenario hashes, objective version, git commit,
and source hash (including uncommitted changes). Timestamps are UTC. Different
configurations never overwrite each other. Existing completed runs are audited
before resume. A failed retry may replace the same deterministic run identity.

Aggregation replays physics and verifies dependency/configuration hashes. Structural
failures never enter scientific summaries. All failures and incomplete runs remain
in `failures.csv`; incompleteness is not a structural failure. `per_run.csv` includes
every record. `main_*` are table-layout names, not claims that the main study ran:
the study column explicitly separates pilot/main/ablations/realtime.

Legacy distance plots use complete-service runs only. V2 tables also disclose raw
distance means beside service, explicitly descriptive rather than rankings.
Paired vehicle differences require
equal service counts; paired distances additionally require equal vehicle counts.
Algorithm seeds are averaged within instance/scenario before descriptive CIs.
Intervals are undefined for fewer than two environmental observations; no test of
significance is performed. Mean run-p95 is not a pooled decision-latency percentile.

Selected legacy transient folders remain gitignored. The V1 publication explicitly
included all704 indexed raw records, calibration revisions and preserved campaign
history. V2 raw records are copied byte-for-byte from local SSD, checksummed and
indexed in `paper_v2/raw_index.csv`. Nothing is committed or pushed automatically.

## Cancelled Campaign History

The run formerly authorized on 2026-10-03 used `results/campaigns/final/`, separate from
the earlier smoke outputs. `manifest.json` freezes source/configuration and counts;
`status.json` is updated every ten seconds with current run, progress and failures.
`parallel_stdout.log` and `parallel_stderr.log` record the authorized multicore
execution. The runner executes pilot (40), ablations (69), realtime (108), and
main (16,800), with up to four memory-aware workers. Realtime and parallel-agent
comparisons have isolation barriers. Concurrent experiment timings are explicitly
separated through `summaries/timing_context.csv` and raw execution-profile fields.
No budget, instance or seed is silently reduced.

Each study writes gzip-compressed full raw records and is followed by audit,
CSV/LaTeX tables and PNG/CSV figures. The runner stops if free space drops below
10 GiB or solver source changes; it never labels partial execution as final.
The old runner is disabled. Do not resume the cancelled campaign.
Completion is recorded only after every configured job and report is processed;
algorithm/structural failures remain explicit in the status and reports.

The paragraphs in this history section describe the former runner, not current
authorization. Full paper execution is blocked pending scientific review.

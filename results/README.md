# Research Outputs

The original smoke runs, the cancelled campaign's 58 completed runs, and the
performance/calibration checks are development evidence, not a finished paper
campaign. The compact replacement has not been launched. See `performance/` and
`docs/performance_results.md` for measurements and the launch gate. The smoke sample
is unbalanced across DoD: zero DoD has only c101C5; DoD 0.5 has five instances.
Do not interpret its lines as controlled dynamicity effects.

```text
results/
  performance/               Profiles, calibration, exactness checks, runtime gate
  campaigns/final/           Cancelled 17,017-job design; 58 completions preserved
  paper/                     Future compact-study reports, after explicit launch
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

Every figure now has a 300-dpi PNG and an exact-data CSV; no PDFs are written. There is no
per-run figure loop. Fixed selection lives in `configs/representative.yaml`.
The chosen incomplete run remains chosen; its unserved request is visible.

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

Distance means use complete-service runs only. Paired vehicle differences require
equal service counts; paired distances additionally require equal vehicle counts.
Algorithm seeds are averaged within instance/scenario before descriptive CIs.
Intervals are undefined for fewer than two environmental observations; no test of
significance is performed. Mean run-p95 is not a pooled decision-latency percentile.

Raw run/trace JSON and temporary logs are gitignored to prevent large transient
outputs flooding history. Summaries, configs, documentation, table exports, selected
figures, and archive history remain versionable. Nothing is committed automatically.
Regenerate raw records with the documented commands before re-auditing on a clone.

## Full Campaign

The full run authorized on 2026-10-03 uses `results/campaigns/final/`, separate from
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
`python -m scripts.run_full_campaign --workers 4` resumes after an interruption.
Completion is recorded only after every configured job and report is processed;
algorithm/structural failures remain explicit in the status and reports.

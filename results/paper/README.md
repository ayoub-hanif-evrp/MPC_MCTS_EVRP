# Completed Paper Campaign

**V1 diagnostic archive, not final paper results.** V1 used the static reference
fleet size as a hard online fleet cap. All executions passed physical/information
audits, but all paper runs were incomplete. A byte-verified snapshot is preserved
under `results/paper_v1_fixed_fleet`. Current diagnostics and their limitations are
in [the V2 report](../paper_v2/PAPER_RESULTS.md).

All 704 unique conditions are complete: 680 newly executed runs and 24 reused
calibration runs. Studies A-E contain 224, 384, 90, 84 and 24 table rows,
respectively; shared conditions are not independent replications.

The saved reports for every study contain zero execution failures and zero
structural audit failures. Every run reports incomplete customer service. This
is a scientific outcome, not a claim that all customers were served.

- `A/` through `E/`: summaries, audit reports, CSV/LaTeX tables, PNG figures and
  figure-data CSVs. There are 40 PNG figures and no PDF figures.
- `raw/`: the 680 new compressed records, copied byte-for-byte from local SSD.
- `raw_index.csv`: all 704 unique job keys, repository-relative record paths,
  SHA-256 checksums and timing contexts. All copies were hash-verified.
- `../performance/calibration_archive/raw/`: both 24-run calibration revisions;
  the index selects the exact 24 records reused by this campaign.
- `execution_metadata/`: original completion status, execution ledger, manifest
  and measured reference-preparation timings.
- `memberships.json`: shared study membership; `timing_context.csv` preserves
  the original runtime paths and execution contexts.

Original raw records and execution metadata retain their original absolute
paths for provenance. Use `raw_index.csv` to locate files in another checkout.
Do not treat isolated and concurrent planning times as interchangeable.

`docs/performance_results.md` and the saved campaign estimate are historical
prelaunch measurements, not the current completion status. The original
17,017-job campaign remains cancelled; its preserved records are separate under
`results/campaigns/final`.

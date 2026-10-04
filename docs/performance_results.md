# Measured Prelaunch Results

Gate: **PASSED. This check does not launch any jobs. Explicit user execution is still required.**

The old 17,017-run campaign is cancelled; its 58 completed runs are preserved.
The replacement paper campaign has NOT been launched. No changes were pushed to GitHub.

## Runtime and Search

The unprofiled pre-optimization c101_21 control at 32 iterations took 167.988 seconds.
- Optimized 8 iterations: 1.529 s, median decision 0.012 s, p95 0.027 s, service 64/100.
- Optimized 16 iterations: 3.682 s, median decision 0.026 s, p95 0.062 s, service 67/100.
- Optimized 32 iterations: 9.692 s, median decision 0.057 s, p95 0.150 s, service 66/100.
- Optimized 64 iterations: 14.864 s, median decision 0.103 s, p95 0.241 s, service 65/100.

These isolated calibration times include cached dependency loading, result creation and serialization; cold reference generation is counted separately below.
The baseline/final profiling JSON files retain action, transition, escape, proposal, MCTS phase, coordinator, serialization and per-agent simulation measurements.

| Iterations | Before profile s | Final profile s | Mean branch before/final | Max branch before/final | Transition calls before/final |
| ---: | ---: | ---: | --- | --- | --- |
| 8 | 59.656 | 2.906 | 179.80 / 12.66 | 1148 / 34 | 3,911,308 / 48,231 |
| 16 | 145.323 | 9.079 | 200.96 / 13.70 | 1156 / 34 | 8,720,860 / 107,017 |
| 32 | 464.286 | 20.031 | 229.53 / 15.33 | 1337 / 34 | 20,343,769 / 250,625 |

## Selected Budget

**16 iterations per agent replan**, common across all test instances.
Smallest budget within one median service and 5% distance on every equal-service/equal-fleet pair
Distance is compared only on equal-service/equal-vehicle pairs. The 8-iteration candidate has no such pairs against the selected reference budget; absence of pairs is not evidence of distance equivalence.
Symmetry reuse remains disabled because it changed physical traces and materially worsened one small-instance distance.

## Calibration Table

All 24 rows passed independent physical, commitment, hidden-information, and provenance audits. Incomplete service remains an outcome, not an execution error.

| Instance | Budget | Served | EVs | Distance | Planning s | Median epoch s | p95 epoch s | Expanded nodes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| c101_21 | 8 | 64 | 13 | 1349.96 | 1.391 | 0.012 | 0.027 | 1317 |
| c101_21 | 16 | 67 | 13 | 1656.88 | 3.551 | 0.026 | 0.062 | 2566 |
| c101_21 | 32 | 66 | 13 | 1687.14 | 9.551 | 0.057 | 0.150 | 4968 |
| c101_21 | 64 | 65 | 13 | 1695.96 | 14.686 | 0.103 | 0.241 | 8192 |
| c201_21 | 8 | 45 | 5 | 773.89 | 1.679 | 0.026 | 0.061 | 558 |
| c201_21 | 16 | 40 | 5 | 802.71 | 3.129 | 0.061 | 0.109 | 990 |
| c201_21 | 32 | 27 | 5 | 483.52 | 3.161 | 0.076 | 0.172 | 1420 |
| c201_21 | 64 | 26 | 5 | 446.27 | 5.718 | 0.171 | 0.341 | 2542 |
| r101_21 | 8 | 66 | 20 | 1396.69 | 1.975 | 0.014 | 0.042 | 2125 |
| r101_21 | 16 | 64 | 20 | 1585.57 | 4.304 | 0.029 | 0.079 | 3927 |
| r101_21 | 32 | 61 | 20 | 1562.74 | 7.343 | 0.039 | 0.141 | 6331 |
| r101_21 | 64 | 63 | 20 | 1793.11 | 13.626 | 0.062 | 0.308 | 11377 |
| r201_21 | 8 | 46 | 4 | 953.00 | 1.901 | 0.029 | 0.064 | 515 |
| r201_21 | 16 | 48 | 4 | 1020.50 | 4.060 | 0.068 | 0.133 | 1062 |
| r201_21 | 32 | 47 | 4 | 886.21 | 6.828 | 0.122 | 0.216 | 2032 |
| r201_21 | 64 | 43 | 4 | 940.83 | 10.585 | 0.192 | 0.342 | 3695 |
| rc101_21 | 8 | 67 | 21 | 1791.34 | 2.522 | 0.017 | 0.040 | 2857 |
| rc101_21 | 16 | 78 | 21 | 2171.06 | 5.393 | 0.030 | 0.100 | 4772 |
| rc101_21 | 32 | 71 | 21 | 2163.90 | 10.786 | 0.057 | 0.183 | 8090 |
| rc101_21 | 64 | 79 | 21 | 2118.83 | 16.847 | 0.079 | 0.213 | 12808 |
| rc201_21 | 8 | 40 | 5 | 1152.20 | 1.684 | 0.032 | 0.076 | 519 |
| rc201_21 | 16 | 42 | 5 | 1213.95 | 2.985 | 0.047 | 0.121 | 998 |
| rc201_21 | 32 | 44 | 5 | 1166.43 | 5.624 | 0.106 | 0.207 | 1888 |
| rc201_21 | 64 | 47 | 5 | 1246.32 | 10.969 | 0.193 | 0.355 | 3944 |

## Jobs and Resource Gate

| Study | Table cells | Unique conditions | Additional runs | Reusable |
| --- | ---: | ---: | ---: | ---: |
| A | 224 | 224 | 224 | 6 |
| B | 384 | 384 | 336 | 6 |
| C | 90 | 90 | 72 | 6 |
| D | 84 | 60 | 48 | 24 |
| E | 24 | 24 | 24 | 0 |

Total unique jobs: 704; reusable: 24; remaining: 680.
Selected outer workers: 4 on 16 physical cores. Measured peak per process 183.3 MiB; reservation 275.0 MiB/worker plus 512 MiB system margin. BLAS threads: 1.
Realtime runs execute after the outer pool exits, with separate timing labels. No nested throughput pools.

- Sequential: 6.29 hours.
- Selected workers: 2.67 hours.
- Cold reference work, before parallelism: 4.72 hours.

Worst measured coordinated time for untimed algorithms/instances; 70% outer efficiency; realtime isolated; cold preparation by family (worst observed fallback), independent instances prepared in parallel.
Extrapolation, not a guarantee. Untested dynamicity, full charging and instance geometry can change runtime.

## Cold Reference Verification

| Instance | Exact recomputation seconds | Reference content hash unchanged |
| --- | ---: | --- |
| c101_21 | 73.317 | True |
| r201_21 | 488.117 | True |
| rc201_21 | 407.939 | True |

The originally measured cold setup costs for r201_21 and rc201_21 were 3665.453 and 3382.607 seconds. Prefix caching and exact geometry reuse do not change their reference schedules or scenario release bounds.

## Launch

Estimate first:

```powershell
python -m evrp.cli estimate --config configs/paper.yaml --workers 4 --output "$env:LOCALAPPDATA\EVRP\paper"
```

Only after reviewing a passing gate and explicitly deciding to launch:

```powershell
python -m evrp.cli paper --config configs/paper.yaml --workers 4 --output "$env:LOCALAPPDATA\EVRP\paper" --execute
```

Summary tables and PNG figures with exact-data CSVs are copied to results/paper. Raw traces remain on the local SSD. Changing the calibrated method/source closes the gate.

## Verification

- Full regression suite: 147 passed in 7.69 s.
- Four external reference-validation cases passed.
- All 24 calibration runs and all three final profiles passed physical/information audits.
- Three pre-optimization golden physical traces matched with action reduction disabled.
- All 24 calibration physical traces, events and non-timing metrics matched across the exact-cache revisions.
- Seven reference-prefix traces and three complete reference content hashes matched exactly.
- Original benchmark inputs unchanged; git diff --check passed.
- PNG figures only, with underlying CSVs; no new PDF figures.

Detailed measured bottlenecks and implementation changes: [performance_analysis.md](performance_analysis.md).

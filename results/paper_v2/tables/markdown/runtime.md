| algorithm | DoD | Runs | Mean_run_planning_s | Mean_epoch_s | Mean_run_p95_s | Max_epoch_s | Mean_simulations |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Coordinated | 0.000 | 6 | 1476.80 | 0.259 | 0.665 | 2.28 | 668704.00 |
| Coordinated | 0.500 | 6 | 748.68 | 0.960 | 5.11 | 13.78 | 367744.00 |
| Greedy | 0.000 | 6 | 0.062 | 0.000 | 0.002 | 0.004 | 0.000 |
| Greedy | 0.500 | 6 | 0.097 | 0.000 | 0.001 | 0.006 | 0.000 |
| Independent | 0.000 | 6 | 18.00 | 0.110 | 0.393 | 3.14 | 17808.00 |
| Independent | 0.500 | 6 | 10.57 | 0.041 | 0.127 | 0.495 | 20240.00 |

All online measurements are concurrent diagnostics, outer workers only, BLAS threads1. Mean run p95 is not a pooled p95. Observer/audit/serialization time is excluded from planning time. No V2 realtime experiment was run.

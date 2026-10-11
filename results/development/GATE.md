# Final-Track Development Gate

GATE = FAIL

The six development instances are not holdout evidence.
The gate requires coordinated static 6/6 complete, dynamic mean >=98%,
dynamic >=5/6 complete, all target DoDs realized, valid replays,
and each coordinated run's event-planning p95 <=5 seconds.

- Coordinated dynamic mean service is below 98%
- Coordinated dynamic service must be complete on at least five instances
- Coordinated static service must be complete on all six instances
- Coordinated run-level p95 planning time exceeds 5 seconds

| Algorithm | Static complete /6 | Dynamic complete /6 | Dynamic mean service |
|---|---:|---:|---:|
| RH_REGRET | 2 | 0 | 0.848 |
| INDEPENDENT_MPC_MCTS | 0 | 0 | 0.902 |
| COORDINATED_MPC_MCTS | 1 | 0 | 0.885 |

Maximum coordinated run-level p95: 7.848 s.
Source SHA-256: `6bea24e2211d179ba464b202f3fe4f7b1556aa5fbd85f959e3c5be9588cdc0af`.
Config SHA-256: `b69a2d9f4ef78b80272c0dac537098729813da402baa93802a761643e113e116`.
Manifest: `C:\Users\AYOUB\OneDrive - EMSI\Bureau\PHD_WORK\MPC_MCTS_Multi_agents_EVRP\results\development\attempts\6bea24e2211d_b69a2d9f\manifest.json`.

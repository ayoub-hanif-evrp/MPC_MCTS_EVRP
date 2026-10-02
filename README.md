# Event-Triggered Coordinated Multi-Agent MPC for D-EVRPTW-PR

Python 3.11+ research framework for the Dynamic Electric Vehicle Routing Problem
with Time Windows and Partial Recharging. Each EV owns an explicit MPC controller;
MCTS approximately solves its deterministic finite-horizon planning problem. A
central assignment coordinator selects compatible first actions. Predicted tails
are intentions, never customer reservations.

**Research status:** the physical model, reference schedules, dynamicization,
event simulator, MPC/MCTS components, baselines, experiment tools, and tests are
implemented. The requested *distance-only* coordination objective admits the
all-Wait solution. This is demonstrated by a regression test and recorded smoke
results. A service requirement must be settled before the proposed method is a
usable routing policy or its performance can support research claims. No service
penalty or service-first objective has been silently substituted.

## Research Question

Can event-triggered coordinated multi-agent MPC, with MCTS-based finite-horizon
optimization and partial charging, improve online service and route distance
under a fixed fleet and hard physical constraints? This implementation is reactive:
it does not predict, sample, or inspect unreleased requests.

## Data and Physical Model

Only the existing Schneider files in `data/evrptw_instances/` are used. They are
read-only. There are 92 instance files and one format readme. The parser validates
all parameters and never supplies missing values.

| Field | Meaning |
| --- | --- |
| `StringID`, `Type` | Unique ID; `d` depot, `f` charging station, `c` customer |
| `x`, `y` | Euclidean coordinates |
| `demand` | Freight consumed by serving the customer |
| `ReadyTime`, `DueDate` | Earliest/latest service start; early waiting allowed |
| `ServiceTime` | Duration of customer service |
| `Q`, `C` | Battery capacity and initial freight capacity |
| `r`, `g`, `v` | Energy/distance, time/charged-energy, and travel speed |

For an arc `(i,j)`, `d_ij = hypot(x_i-x_j, y_i-y_j)`, travel time is
`d_ij/v`, energy consumption is `r*d_ij`, and charging duration is `g*delta_energy`.
Internal values retain floating-point precision. Each homogeneous EV starts at the
depot with SOC `Q` and remaining capacity `C`. Serving `i` consumes `demand_i`.
Battery, capacity, service-start deadlines, and final return are hard constraints.

One EV executes one depot-to-depot tour. Stations have unlimited simultaneous
capacity and may be revisited after customer service. Charging occurs only at
station nodes, including the distinct station `S0` coincident with the depot.
There are no charger queues, reloads, stochastic traffic, or heterogeneous EVs.

## Architecture

```text
EVAgent -> MPCController -> MPCPlanningProblem -> MCTSOptimizer.solve()
    |                         H_p customer services; H_c = 1
    +---- top-L distinct first-action proposals + safe fallback ----+
                                                                 |
                                                         Coordinator
                                                                 |
                                                   EventDrivenSimulator
                                                                 |
                                           new observation -> new MPC problem
```

`evrp/model.py` is the authoritative deterministic transition/feasibility engine.
`Observation` contains public infrastructure, currently available customers, and
currently committed customer IDs. Agents receive no global state, scenario,
future release calendar, or hidden customer count.

`ServeCustomer` covers travel, early waiting, and service. `RechargeAt` covers
travel and positive-energy charging. Both are non-preemptive. Passive Wait is
interruptible by an external event and has a safe-return deadline determined from
public information. Simultaneous events are processed before planning.

MPC defines the measured state, deterministic transition, constraints, customer
service horizon, one-action control horizon, distance stage cost, and feasible
return-distance terminal cost. Charging actions do not consume a customer-service
horizon step. UCT uses negative predicted cost, seeded heuristic rollouts, and
fixed-iteration or wall-clock budgets. Results are **best-found MCTS plans**.

The coordinator minimizes summed proposal costs subject to exactly one proposal
per ready EV and at most one immediate commitment per customer. Non-customer
actions do not conflict. A separate fallback is available even with `L=1`.
See [methodology](docs/methodology.md) for the formulation and objective issue.

## Reference Schedules and Scenarios

The reference heuristic uses multiple seeded time-window-aware insertion starts,
full-charge station repair, feasible relocate improvement, and lexicographic
comparison by route count then distance. It explicitly fails if it cannot serve
every customer. The selected route count determines the shared fleet size `K`.
Reference traces include node sequence, travel/service/charge times, and SOC.

Dynamic requests use **reference-schedule-preserving dynamicization inspired by
Yang et al.** For customer `i`, the release upper bound is
`min(ReadyTime_i, reference_predecessor_departure_i)`. A selected eligible customer
receives a seeded uniform draw in `(0, upper_bound]`; others are released at zero.
Uniform sampling is our experimental choice, not a claim about Yang's distribution.
The files are not the original Yang benchmark. Both Bernoulli and exact-count
selection record target and realized DoD; zero-bound customers are ineligible.

Generated JSON files live in `data/reference_schedules/` and
`data/generated_scenarios/`, with benchmark hashes and reference identifiers.
The online algorithms never receive the reference schedule.

## Reproduction

From the repository root:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
python -m evrp.cli scenario --instance c101C5 --config configs/debug.yaml
python -m evrp.cli run --instance c101C5 --config configs/debug.yaml --algorithm GREEDY
python -m evrp.cli run --instance c101C5 --config configs/debug.yaml --algorithm COORDINATED_MPC_MCTS
python -m evrp.cli smoke --config configs/debug.yaml --output results/smoke
python -m evrp.cli benchmark --config configs/benchmark.yaml
python -m evrp.cli ablations --config configs/ablations.yaml
python -m evrp.cli aggregate --input results/runs --output results/aggregate
python -m evrp.cli plot --input results/runs --output results/figures
```

The coordinated command currently reproduces the documented all-Wait degeneracy.
Use GREEDY to inspect actual online routing while the objective is being resolved.
`--dynamicity`, `--scenario-seed`, and `--scenario path/to/file.json` are supported.
The scenario's reference and fleet must match the configured reference solver.

Do not run the full grids during development. The smoke command runs only C5 at
DoD 0 and 0.5, R5, RC5, C10, C15, and one `c101_21` case with a deliberately tiny
MCTS budget. The default main grid includes all local `_21` families, five DoDs,
multiple scenario/algorithm seeds, and all baselines. Ablations vary one factor at
a time: horizon, top-L, budget, charging, coordination, parallelism, and DoD.

## Baselines and Outputs

- `GREEDY`: urgency/proximity-aware, energy-safe myopic service with charging repair.
- `MPC_MCTS_H1`: coordinated MPC with one predicted customer service.
- `INDEPENDENT_MPC_MCTS`: deterministic vehicle-order conflict resolution without global assignment.
- `COORDINATED_MPC_MCTS`: top-L first-action minimum-cost assignment.
- `STATIC_REFERENCE`: offline feasible reference, explicitly not a fair online competitor.

Each run writes a JSON file with effective configuration, source/data hashes,
package versions, metrics, events, physical traces, selected plans, MCTS statistics,
and trace-audit results. Completed records resume by content-derived identity;
failures are written with diagnostics and retried on a subsequent invocation.
Unserved customers make `feasible=false`, even when every physical action is legal.

Aggregation retains failed/infeasible runs and reports sample counts, mean, median,
sample standard deviation, and descriptive Student-t 95% intervals. Paired
differences use identical instance, scenario identifier, algorithm seed, and source
hash. No significance is inferred from a single run. Matplotlib produces geometry,
route, SOC, release, dynamicity, latency, and ablation figures.

Sequential fixed-iteration runs reproduce logical decisions. Measured runtimes and
wall-clock search results are not bitwise reproducible. Process-based parallel
planning preserves seed streams and ordering, but startup overhead may dominate
small instances.

## References

- Schneider, Stenger, Goeke (2014), *The Electric Vehicle-Routing Problem with Time
  Windows and Recharging Stations*. [DOI: 10.1287/trsc.2013.0490](https://doi.org/10.1287/trsc.2013.0490).
- Keskin and Catay (2016), *Partial recharge strategies for the electric vehicle
  routing problem with time windows*. [DOI: 10.1016/j.trc.2016.01.013](https://doi.org/10.1016/j.trc.2016.01.013).
- Yang et al. (2017), *Dynamic vehicle routing with time windows in theory and
  practice*. [DOI: 10.1007/s11047-016-9550-9](https://link.springer.com/article/10.1007/s11047-016-9550-9).
- Caillard and Ben Chabane (2024), *Evolutionary-Based Ant System Algorithm to Solve
  the Dynamic Electric Vehicle Routing Problem*. [DOI: 10.5220/0012379200003639](https://www.scitepress.org/Link.aspx?doi=10.5220%2F0012379200003639).
- Kocsis and Szepesvari (2006), *Bandit based Monte-Carlo Planning*.
  [Paper](https://aima.cs.berkeley.edu/~russell/classes/cs294/s11/readings/Kocsis%2BSzepesvari%3A2006.pdf).

All algorithm code is independently implemented. See
[assumptions](docs/assumptions.md) and [implementation audit](docs/implementation_report.md).

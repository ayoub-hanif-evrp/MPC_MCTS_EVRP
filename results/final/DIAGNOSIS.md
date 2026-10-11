# Diagnosis of the Frozen 32-Iteration Screen

Source: `results/screening/stage1/` and `results/screening/GATE.md`. These are
development observations from the previous implementation, not holdout evidence.

| Instance | K_ref | Static RH / Independent / Coordinated | Dynamic RH / Independent / Coordinated |
|---|---:|---:|---:|
| c101_21 | 13 | 93 / 87 / 91 | 81 / 81 / 76 |
| c201_21 | 5 | 100 / 79 / 70 | 93 / 95 / 76 |
| r101_21 | 20 | 89 / 90 / 91 | 84 / 82 / 77 |
| r201_21 | 4 | 72 / 68 / 77 | 76 / 83 / 96 |
| rc101_21 | 21 | 100 / 100 / 100 | 86 / 84 / 83 |
| rc201_21 | 5 | 92 / 83 / 68 | 90 / 89 / 89 |

Only `rc101_21` was complete for coordinated static service; none of the six
dynamic coordinated runs were complete. All runs passed physical and information
boundary replay checks. The configured nominal 32-iteration rule exceeded 32 in
94 of 6,968 searches because root coverage was mandatory (maximum 34).

## Failure Classification

- **Future assignment locking: demonstrated mechanism and strong lead.** The old
  `preserve_continuation` appended every future customer from an incumbent route
  to new proposals. `route_observation` hid the other vehicles' future customers.
  The disk audit then required every predicted customer to be served by its
  previous owner. On static `c201_21`, epoch 0 assigned 70 customers, including
  55 by repair. Epoch 1 had 46 customers in busy route backgrounds and zero new
  repair insertions. RH_REGRET completed all 100 with the same five physical EVs,
  ruling out fleet count alone as an explanation for that condition. The exact
  marginal service loss from locking remains unmeasured until the correction runs.
- **Customer candidate pruning: present, not isolated as the cause.** In each
  incomplete coordinated static run, the old direct-next-service diagnostic
  reported roughly 74-79% of sampled direct opportunities absent from local
  roots. This mixes ownership masking with candidate pruning and excludes
  charging-mediated work; the percentage is not a causal pruning estimate.
- **MCTS selection and route diversity: plausible.** All *generated* root actions
  were visited. Their union was much smaller than the released pool; static
  `c201_21` epoch 0 had 27 customers in candidate intents out of 100 available.
  Root coverage does not imply that good multi-customer routes were found.
- **Regret repair: service shortfall and high cost demonstrated.** Static
  `c201_21` grew from 27 candidate-intent customers to 70 after 55 insertions, but
  no further insertions occurred at the next seven recorded epochs. Repair took
  573 of 580 measured planning seconds on that run. The reason each remaining
  customer failed insertion has not been recorded per position, so physical
  infeasibility must not be inferred.
- **Charging and path construction: unresolved.** Construction only tries direct
  travel, bounded single-station partial-charge bridges, then a full-charge
  connection. Failure may miss a feasible charging schedule. The old traces do
  not distinguish this from time windows or locked route order.
- **Waiting and returning: no sampled premature return found.** The old observer
  recorded zero premature returns in all coordinated runs. It did record 31 long
  waits with directly feasible work in static `c201_21`; this is observational,
  not proof that those customers were actually admissible to the waiting EV.
- **Insufficient physical fleet: not established.** Static `c201_21` has a
  complete five-EV comparator. In other cases, all algorithms are incomplete;
  heuristic `K_ref` is not a proof of a minimum fleet and a larger fleet is not
  authorized as a correction.

The first correction is to keep the old feasible suffix as an incumbent while
releasing its future customers for assignment at the next ready decision. Physical
actions already dispatched remain non-preemptible. This directly addresses the
demonstrated lock and keeps the original scenarios and fixed fleets.

## Post-Correction Development Evidence

The frozen 48-iteration development attempt completed all 36 prescribed runs.
Its audited gate is `results/development/GATE.md` (FAIL). Coordinated static
service was complete on only 1/6 instances; dynamic mean service was 88.5%,
with 0/6 complete. Its worst run-level event-planning p95 was 7.848 seconds,
above the configured five-second bound. No physical or information-boundary
violation was reported by the run audits.

The flexible-suffix change helped some cases, notably dynamic `c101_21`
(76 to 93 served), but did not resolve the constrained-fleet cases. Static
`c201_21` improved from 70 to 76 served, while `r201_21` fell from 77 to 70;
these comparisons also include the updated search/repair configuration and
are not isolated causal estimates of the suffix change.

At the first decision of static `c201_21`, 100 customers were available,
candidate routes covered 54, the coordinated selection covered 25, and regret
repair raised coverage to 74. At the first static `r201_21` decision the same
figures were 100, 52, 20, and 60. All 24 final unserved `c201_21` customers
appeared in a top-L proposal at some point, but only three appeared in a
selected intent. The corresponding figures for `r201_21` were 30 and three.
This is evidence of limited route combination and downstream insertion, not
proof that more root candidates or MCTS iterations would restore full service.
The diagnostic labels `SEARCH_NEVER_SELECTED` for 23/24 and 30/30 of these
unserved customers, respectively. These labels do not prove global physical
feasibility of completing all requests with the fixed fleet.

No further algorithmic correction is made. The one permitted small adjustment
is not supported by the observed failure mode, and increasing search would
worsen an already failed latency gate. The method remains frozen at this failed
development result; the disjoint holdout has not been inspected or executed.

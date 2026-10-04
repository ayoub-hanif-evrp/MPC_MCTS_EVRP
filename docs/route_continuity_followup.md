# Executable Route Continuity: Experimental Follow-Up

This is an opt-in methodological change, not a silent correction to archived
V2. Both `route_continuity` and `route_insertion` default to false. Full paper
execution remains blocked. See the [measured results](../results/development_route_continuity/README.md).

## Continuity

Let T_k be the retained unexecuted suffix through the last predicted service,
and R_k its customer set. Require R_j intersect R_k to be empty for distinct
vehicles. A controller observes unallocated known requests plus its own R_k;
reserve planning observes only unallocated known requests. These are allocation
masks on released data, never access to hidden requests.

At feedback, replay T_k from the measured state through the authoritative
transition model. Keep it as a candidate even when MCTS or Top-L cannot recover
it. A replacement must cover every customer in R_k. Busy coverage counts only
executable obligations. Coordination enforces disjoint full customer sets,
not just distinct first actions. Independent selection uses the same ownership
constraints deterministically. Only the first physical action is dispatched.
Terminal WAIT/RETURN predictions after the last service are not retained,
allowing route extension before permanent return.

Obligations restrict optimization and can prevent a better later reassignment.
This is not claimed to solve global fleet minimization.

## Optional Insertion

Before reserve admission, process unallocated released requests in due-date,
then customer-ID order. Try every insertion position in active suffixes; choose
minimum additional predicted distance, completion time, vehicle ID and position.
Replay the full suffix with safe-return feasibility. No additional station-repair
search is introduced by this insertion heuristic.

For busy EVs, start prediction at the AFTER state of the immutable current action.
This allocates work after completion without preemption. Finished/returning routes
and stale non-ready idle states are ineligible. Suffix service count cannot exceed
the local horizon at that origin (Hp1 for Greedy); a currently executing service
precedes it. Insertion runtime is included in planning time, not MCTS simulations.
Retained or inserted suffixes are feasibility certificates, not UCT simulations.

All methods share this fleet manager. Independent means independent local MCTS
selection within common ownership/insertion, not fully decentralized allocation.
A paper must explicitly describe this change from the intent-only baseline.

## Evidence and Limits

Two preserved36-condition grids compare continuity alone and plus insertion.
Scenarios, seeds, budget32, horizon and limits match. Source revisions differ
because insertion was added between grids; snapshots and hashes are retained.
Four initial probes per revision are reused, not counted twice.

All coordinated static cases serve100/100, with zero selected WAITs in both grids.
Insertion reduces dynamic EVs but coordinated rc101_21 still misses two customers.
Independent and Greedy lose additional customers in some insertion controls.
No universal improvement or paper readiness is claimed; no full campaign was run.

Disk audits verify every route promise and insertion against actual future service
by that owner, plus physical replay and release safety. Existing defaults and
V1/V2 record compatibility remain supported. The scientific gate remains closed.

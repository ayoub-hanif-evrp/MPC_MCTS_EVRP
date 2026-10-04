# V2 Fleet and Search Diagnostics

V1 remains replayable with `fleet_mode=fixed_reference`,
`require_root_coverage=false`, and `max_idle_wait=0`. These legacy defaults are
retained solely for existing configuration/record compatibility. V2 diagnostic
configurations explicitly opt into `lazy_reserve`, root coverage, and a 10-unit
maximum interruptible wait. This is a method revision, not an exact optimization.

## Exchangeable Reserve

Let n be the instance customer count, A(t) the set of instantiated vehicles and
R(t)=n-|A(t)| the unused reserve count. Every unused vehicle has the same depot,
time, full battery, full payload, empty service history, observation and MPC
configuration. For any permutation of unused IDs, their physical action/transition
sets are identical. One depot-template search therefore supplies a common menu
of distinct first-customer anchors, instead of R(t) independent randomized trees.
This deliberately changes the joint proposal distribution; no equivalence to
independently seeded unused-vehicle searches is claimed.

Each virtual option chooses a new-route proposal or a zero-activation idle option.
The coordinator enforces at most R(t) activations, at most one reserve anchor per
customer, and first-service exclusivity with active vehicles. A charge-first
anchor prevents duplicate reserve launches while that charge is committed; it
does not irrevocably reserve the predicted customer after feedback. A physical ID
and EVAgent are created only for a selected departure. Unused pool members neither
acquire histories nor count as activated vehicles. Active and finished routes
are never merged, reloaded, or reactivated. This is a non-binding operational
reserve assumption, not a claim that n routes will always suffice for any online
policy: wasted empty tours can still exhaust that bound.

## Predicted Coverage

Coordinated coverage is the union of selected ready-vehicle/reserve intentions
and the currently available customer IDs in busy vehicles' last predicted tails.
These background intentions disappear on action completion and are recomputed
after feedback. They contain only previously revealed customers; newly hidden
requests cannot enter them. They are optimistic predictions, not commitments or
a promise of future service. The three exact MILP stages still maximize this
union, then minimize new activations, then predicted distance. Independent/Greedy
selection remains local, with deterministic conflict resolution and no joint
tail-coverage optimization. This difference and its fleet consequences must be
reported, not hidden as a solver detail.

Reserve departure can expose the next bounded customer shortlist at the same
simulation time. Such a repeat requires a strictly positive number of activations
and consumes the finite pool; it cannot create an infinite zero-time loop.

## Root Coverage and Time

For b admissible root actions and nominal total budget B, iteration-mode MCTS
runs max(b,B) simulations. Each root action is expanded and rolled out once before
UCT may revisit a child. Root action count, evaluated count, minimum visits,
coverage fraction, and actual simulations are recorded, including terminal roots.
For wall-clock mode, mandatory coverage takes precedence over the nominal time
limit and is fully charged. V2 realtime validation is deferred.

Idle WAIT is interruptible by a new release or its own expiration, not by every
unrelated vehicle completion. The active physical state is synchronized with an
auditable wait transition before replanning. A reserve pool remains available
even when every active tour has ended. If no known customer passes even the cheap
capacity/time necessary checks, an active vehicle follows its safe return instead
of repeatedly waiting; this deliberately sacrifices the option of retaining that
active tour for unseen demand, while the homogeneous reserve remains available.

The completed diagnostics show that the individual wait bound does not prevent
long cumulative idle spells. Static c201_21 made23943 wait selections and140 long
idle spells with feasible known work at their start. This remains an algorithmic
defect; V2 is not accepted as a final method merely because each WAIT is bounded.

## Diagnostic Limits

Diagnostics are read-only and timed outside the planning interval. Raw feasible
counts mean direct next-service transitions for ready vehicles plus one reserve
template, not exhaustive charging-mediated feasibility or full route feasibility.
Last feasible times are sampled observed decision times, not continuous-time
latest-departure proofs. Candidate appearance is the union of evaluated root
service actions; top-L and selected intent counts are recorded separately.
Final unserved reasons classify this evidence; they are not unique causal proofs.
Reference replay establishes scenario feasibility, but does not make any online
policy optimal. All oracle records are excluded from online comparison tables.

## Diagnostic Budget Rule

Calibrate 32/64/96 nominal total simulations on the six prescribed development
instances at DoD .5, seeds 0. Choose the smallest budget within one customer of
the best median service, requiring at least one equal-service/equal-EV pair with
all paired distances within 5%; largest budget breaks the reference median tie.
Ambiguity defaults to 64. No per-instance tuning and no 250+ budgets.

Then run three online methods on both DoDs, six matched fixed-fleet controls,
and Hp=1/3 controls at DoD .5 to evaluate the requested horizon question.
Shared calibration/main conditions are reused: 66 unique online conditions,
12 separate oracle controls. Full charging, L sweeps, seed robustness, realtime,
and all-56-instance V2 breadth are not measured by this diagnostic design.
The full paper executor is explicitly blocked pending user review.

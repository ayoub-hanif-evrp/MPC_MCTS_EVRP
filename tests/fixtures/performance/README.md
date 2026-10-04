# Pre-Optimization Physical Traces

These three compressed fixtures were recorded before the performance changes,
with 8 MCTS iterations, Hp=5, L=3, DoD=0.5, and both seeds 0. They are small
development regression cases, not paper evidence. The original config, executed
events, and full transitions are retained without rounding.

`python -m scripts.verify_performance` disables action-space reduction and checks
exact transition/event equality after the exact-computation optimizations. It
separately evaluates optional symmetry reuse with the bounded action set.

"""Explicit scientific dependencies; bump when corresponding semantics change."""

OBJECTIVE_VERSION = "service-activation-distance-v2"
REFERENCE_SOLVER_VERSION = "pareto-repair-route-reduction-v2"
SCENARIO_GENERATOR_VERSION = "reference-preserving-v2"
RESULT_SCHEMA_VERSION = 2


def fleet_objective(metrics: dict) -> tuple:
    return (metrics["customers_unserved"], metrics["vehicles_activated"], metrics["total_distance"])

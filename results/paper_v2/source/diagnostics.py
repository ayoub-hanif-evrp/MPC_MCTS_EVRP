"""Read-only sampled opportunity diagnostics; never supplied to an online policy."""

from collections import Counter
from statistics import mean

from .model import Action, InfeasibleAction, transition
from .reserve import depot_template


class ServiceDiagnostics:
    def __init__(self, instance, scenario):
        self.instance, self.scenario = instance, scenario
        releases = dict(scenario.customer_release_times)
        self.customers = {c.id: dict(instance=instance.name, DoD=scenario.target_DoD,
            customer=c.id, release_time=releases[c.id], due_time=c.due,
            last_time_feasible_if_known=None, candidate_appearances=0, times_in_topL=0,
            times_covered_by_intent=0, feasible_epochs=0, pruned_epochs=0,
            fleet_exhausted_epochs=0, failure_reasons={}) for c in instance.customers}
        self.epochs = []

    def observe(self, state, observation, plans, selected, measured_results, reserve_count, config):
        feasible, reasons = set(), {c.id: Counter() for c in observation.customers}
        direct_by_vehicle = {}
        vehicles = [v for k, v in state.vehicles.items() if k not in state.busy and not v.finished
                    and v.time >= state.time-1e-8]
        if reserve_count:
            vehicles.append(depot_template(observation))
        for vehicle in vehicles:
            direct = set()
            for customer in observation.customers:
                try:
                    transition(vehicle, Action("serve", customer.id), observation)
                    direct.add(customer.id)
                except InfeasibleAction as error:
                    reasons[customer.id][str(error.reason)] += 1
            direct_by_vehicle[vehicle.id] = direct
            feasible.update(direct)
        root_ids, top_ids = set(), set()
        stats = []
        for _, result in measured_results:
            stats.append(result.statistics)
            root_ids.update(a["action"]["destination"] for a in result.statistics.root_actions
                            if a["action"]["kind"] == "serve")
            root_ids.update(p.first.destination for p in result.evaluated_proposals if p.first.kind == "serve")
            top_ids.update(c for p in result.proposals for c in p.unique_predicted_customer_set)
        intents = {c for p in selected.values() for c in p.unique_predicted_customer_set}
        for customer in observation.customers:
            row = self.customers[customer.id]
            row["candidate_appearances"] += int(customer.id in root_ids)
            row["times_in_topL"] += int(customer.id in top_ids)
            row["times_covered_by_intent"] += int(customer.id in intents)
            row["fleet_exhausted_epochs"] += int(not reserve_count and not any(not v.departed for v in vehicles))
            if customer.id in feasible:
                row["last_time_feasible_if_known"] = state.time
                row["feasible_epochs"] += 1
                row["pruned_epochs"] += int(customer.id not in root_ids)
            row["failure_reasons"] = dict(Counter(row["failure_reasons"]) + reasons[customer.id])
        returns = [(k, p) for k, p in selected.items() if p.first.kind == "return"]
        waits = [(k, p) for k, p in selected.items() if p.first.kind == "wait" and k >= 0]
        self.epochs.append(dict(time=state.time, visible_customers=len(observation.customers),
            raw_feasible_customers=len(feasible), shortlisted_customers=len(root_ids),
            feasible_customers_pruned=len(feasible-root_ids),
            mean_root_branching=mean(s.root_action_count for s in stats) if stats else 0,
            root_actions=sum(s.root_action_count for s in stats),
            root_evaluated=sum(s.root_actions_evaluated for s in stats),
            minimum_root_visits=min((s.minimum_root_visits for s in stats), default=0),
            actual_simulations=sum(s.iterations for s in stats), reserve_remaining=reserve_count,
            wait_selections=len(waits), return_selections=len(returns),
            finished_while_known_customers_remain=len(returns) if observation.customers else 0,
            premature_returns=sum(bool(direct_by_vehicle.get(k)) for k, _ in returns),
            long_waits_with_feasible_work=sum(bool(direct_by_vehicle.get(k)) and p.first.wait_duration > 10
                                              for k, p in waits)))

    def finish(self, state):
        unserved = []
        for key, row in self.customers.items():
            if key in state.served_customers:
                continue
            if row["feasible_epochs"] and row["pruned_epochs"] == row["feasible_epochs"]:
                reason = "CANDIDATE_PRUNED_REPEATEDLY"
            elif row["feasible_epochs"]:
                reason = "SEARCH_NEVER_SELECTED"
            elif row["fleet_exhausted_epochs"] and self.epochs and max(e["reserve_remaining"] for e in self.epochs) == 0:
                reason = "FLEET_CAP_REACHED"
            elif row["failure_reasons"] and set(row["failure_reasons"]) == {"CAPACITY"}:
                reason = "CAPACITY_UNAVAILABLE"
            elif state.time > row["due_time"]:
                reason = "TIME_WINDOW_EXPIRED"
            elif state.vehicles and all(v.finished for v in state.vehicles.values()):
                reason = "ALL_VEHICLES_RETURNED"
            else:
                reason = "NO_ACTIVE_OR_RESERVE_VEHICLE_COULD_SERVE"
            unserved.append({**row, "final_reason": reason})
        totals = sum(e["raw_feasible_customers"] for e in self.epochs)
        roots = sum(e["root_actions"] for e in self.epochs)
        summary = {"mean_"+name: mean(e[name] for e in self.epochs) if self.epochs else 0
                   for name in ("visible_customers", "raw_feasible_customers", "shortlisted_customers", "mean_root_branching")}
        summary.update(fraction_feasible_pruned=sum(e["feasible_customers_pruned"] for e in self.epochs)/totals if totals else 0,
            root_action_coverage=sum(e["root_evaluated"] for e in self.epochs)/roots if roots else None,
            minimum_root_visits=min((e["minimum_root_visits"] for e in self.epochs if e["root_actions"]), default=0),
            customers_losing_sampled_feasibility=sum(r["feasible_epochs"] > 0 for r in unserved))
        for name in ("wait_selections", "return_selections", "finished_while_known_customers_remain",
                     "premature_returns", "long_waits_with_feasible_work"):
            summary[name] = sum(e[name] for e in self.epochs)
        return dict(summary=summary, epochs=self.epochs, unserved=unserved,
                    reason_counts=dict(Counter(r["final_reason"] for r in unserved)),
                    interpretation="Direct next-service feasibility at observed decision epochs only. Charging-mediated opportunities and between-epoch states are not exhaustively certified. Reasons are diagnostic evidence, not exclusive causal proofs. No hidden records enter planning.")

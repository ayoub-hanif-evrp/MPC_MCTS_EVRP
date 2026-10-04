"""Post-hoc idle-spell analysis of completed diagnostics; never replans a route."""

from collections import defaultdict

import pandas as pd

from evrp.audit import decode_result
from evrp.instance import load_instance
from evrp.model import Action, Observation, transition, InfeasibleAction
from evrp.storage import BENCHMARK, load_json
from scripts.report_v2 import OUT, table


def main():
    manifest = load_json(OUT/"diagnostic_manifest.json")
    keys = {m["key"] for m in manifest["memberships"] if m["phase"] == "main"}
    spells, summaries, roots = [], [], []
    for item in manifest["records"]:
        if item["key"] not in keys:
            continue
        raw = load_json(item["path"])
        result = decode_result(raw)
        instance = load_instance(BENCHMARK/(item["instance"]+".txt"))
        by_id = {c.id:c for c in instance.customers}
        wait_observations = {}
        for d in raw["decisions"]:
            for k,p in d["plans"].items():
                if p["actions"][0]["kind"] == "wait":
                    wait_observations[d["time"], int(k)] = d["available"]
        vehicles = defaultdict(list)
        for s in result.steps:
            vehicles[s.before.id].append(s)
        local = []
        for vehicle, steps in vehicles.items():
            current = None
            for s in sorted(steps, key=lambda step: step.before.time):
                if s.action.kind == "wait" and s.before.departed:
                    if current is None:
                        available = wait_observations.get((s.before.time, vehicle), [])
                        observation = Observation(s.before.time, instance.infrastructure,
                                                  tuple(by_id[c] for c in available))
                        feasible = []
                        for c in observation.customers:
                            try:
                                transition(s.before, Action("serve", c.id), observation)
                                feasible.append(c.id)
                            except InfeasibleAction:
                                pass
                        current = dict(instance=item["instance"], algorithm=item["algorithm"], DoD=item["DoD"],
                            vehicle=vehicle, start=s.before.time, finish=s.after.time, segments=1,
                            known_feasible_at_start=len(feasible), feasible_customer_ids=";".join(feasible),
                            observation_found=(s.before.time,vehicle) in wait_observations)
                    else:
                        current["finish"] = s.after.time
                        current["segments"] += 1
                elif current is not None:
                    local.append(current)
                    current = None
            if current is not None:
                local.append(current)
        for spell in local:
            spell["duration"] = spell["finish"]-spell["start"]
        spells.extend(local)
        summaries.append(dict(Instance=item["instance"], Algorithm=item["algorithm"], DoD=item["DoD"],
            Idle_spells=len(local), Long_spells=sum(s["duration"] > 10+1e-8 for s in local),
            Long_spells_with_feasible_work=sum(s["duration"] > 10+1e-8 and s["known_feasible_at_start"] > 0 for s in local),
            Longest_idle=max((s["duration"] for s in local),default=0),
            Wait_selections=raw["metrics"]["wait_selected"], Total_planning_s=raw["metrics"]["total_planning_time"]))
        searches=[s for s in raw["searches"] if s["root_action_count"]]
        if searches:
            total=sum(s["root_action_count"] for s in searches)
            roots.append(dict(Instance=item["instance"], Algorithm=item["algorithm"], DoD=item["DoD"],
                Searches=len(searches), Mean_root_branching=total/len(searches),
                Max_root_branching=max(s["root_action_count"] for s in searches),
                Root_actions=total, Evaluated=sum(s["root_actions_evaluated"] for s in searches),
                Minimum_visits=min(s["minimum_root_visits"] for s in searches),
                Coverage=sum(s["root_actions_evaluated"] for s in searches)/total,
                Actual_simulations=sum(s["iterations"] for s in searches)))
    pd.DataFrame(spells).to_csv(OUT/"idle_spells.csv",index=False)
    table("idle_spells",pd.DataFrame(summaries),
          "Post-hoc physical idle spells concatenate consecutive completed WAIT transitions on already-departed EVs. Long means >10 simulation-time units. Feasibility is direct next-service at the first recorded WAIT observation. Repeated short waits can create a long spell even when no single WAIT exceeds10. Initial depot reserve waiting is excluded; no policy is rerun.")
    table("root_coverage",pd.DataFrame(roots),"Counts sum actual MCTS searches, including the single reserve-template search; virtual candidate copies are not counted as searches. Every admissible root action is visited; pruned customers are not root actions.")
    print(pd.DataFrame(summaries).query("Algorithm == 'COORDINATED_MPC_MCTS'").to_string(index=False))


if __name__ == "__main__":
    main()

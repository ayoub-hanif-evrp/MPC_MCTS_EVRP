"""Compare physical traces across the two bounded-search calibration revisions."""

from collections import defaultdict
import os
from pathlib import Path

from evrp.storage import load_json, canonical, save_json


def main():
    root = Path(os.environ["LOCALAPPDATA"]) / "EVRP/calibration/raw"
    groups = defaultdict(list)
    for path in root.glob("*.json.gz"):
        result = load_json(path)
        if result["status"] == "completed":
            groups[(result["metadata"]["instance"], result["requested_config"]["mcts_iterations"])].append(result)
    rows = []
    for (instance, budget), records in sorted(groups.items()):
        if len({r["provenance"]["source_sha256"] for r in records}) < 2:
            continue
        reference = records[0]
        for record in records[1:]:
            assert canonical(reference["steps"]) == canonical(record["steps"]), (instance, budget, "steps")
            assert canonical(reference["events"]) == canonical(record["events"]), (instance, budget, "events")
            metrics = lambda r: {k: v for k, v in r["metrics"].items() if "planning_time" not in k}
            assert metrics(reference) == metrics(record), (instance, budget, "metrics")
        rows.append(dict(instance=instance, iterations=budget, identical=True, revisions=len(records)))
    assert len(rows) == 24, "Need both complete 24-case calibration revisions"
    save_json("results/performance/calibration_exactness.json", rows)
    print("All 24 calibration conditions have identical physical steps, events and non-timing metrics across exact-cache revisions.")


if __name__ == "__main__":
    main()

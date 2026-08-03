from __future__ import annotations

import argparse
import json
import subprocess as sp
from datetime import datetime, timedelta
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach actual Modal interval billing to a GPU bake-off report.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--modal-bin", type=Path, required=True)
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--start", required=True, help="Inclusive ISO-8601 interval start.")
    parser.add_argument("--end", required=True, help="Exclusive ISO-8601 interval end.")
    args = parser.parse_args()

    report_path = args.report.expanduser().resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    completed = sp.run(
        [
            str(args.modal_bin.expanduser().resolve()),
            "billing",
            "report",
            "--start",
            args.start,
            "--end",
            args.end,
            "--resolution",
            "h",
            "--tz",
            "local",
            "--show-resources",
            "--json",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    rows = [
        row
        for row in json.loads(completed.stdout)
        if row.get("description") == args.app_name
    ]
    if not rows:
        raise SystemExit("no Modal billing rows matched the app and interval")

    resource_costs: dict[str, float] = {}
    for row in rows:
        resource = str(row["resource"])
        resource_costs[resource] = resource_costs.get(resource, 0.0) + float(row["cost"])
    total_cost = sum(resource_costs.values())
    selected_song_count = max(1, len(report.get("selected_song_ids", [])))
    interval_end = datetime.fromisoformat(args.end)
    collection_complete = datetime.now(interval_end.tzinfo) >= interval_end + timedelta(minutes=5)
    report["actual_billing"] = {
        "evidence_level": (
            "modal_app_interval_attribution_final"
            if collection_complete
            else "modal_app_interval_attribution_preliminary"
        ),
        "attribution_requirement": "one_bakeoff_only_in_app_interval",
        "collection_complete": collection_complete,
        "app_name": args.app_name,
        "interval_start": args.start,
        "interval_end": args.end,
        "resource_costs_usd": {name: round(cost, 8) for name, cost in sorted(resource_costs.items())},
        "total_cost_usd": round(total_cost, 8),
        "actual_cost_per_selected_song_usd": round(total_cost / selected_song_count, 8),
        "credits_and_discounts_included": False,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"report={report_path}")
    print(f"actual_total_cost_usd={total_cost:.8f}")
    for resource, cost in sorted(resource_costs.items()):
        print(f"resource_{resource.lower()}_usd={cost:.8f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

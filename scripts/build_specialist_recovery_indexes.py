from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.specialist_training_contract import (  # noqa: E402
    SPECIALIST_BASE_IDS,
)

FAMILIES = SPECIALIST_BASE_IDS
SOURCE_GROUPS = {
    "real_multitrack": {
        "albumdb",
        "medleydb_sample",
        "onair_music",
        "rawstems",
        "spheres",
        "urmp",
    },
    "isolated_recording": {
        "eg_ipt",
        "freesound_loop_dataset",
        "guitar_techs",
        "idmt_smt_guitar",
        "tinysol",
    },
    "synthetic_score": {
        "chorale_bricks",
        "cocochorales",
        "quartset",
    },
    "synthetic_note": {
        "nsynth",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build source-balanced specialist recovery indexes."
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=ROOT / "training/online_indexes/research_all",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "training/online_indexes/recovery-v1",
    )
    return parser.parse_args()


def source_group(source_id: str) -> str:
    matches = [
        group
        for group, sources in SOURCE_GROUPS.items()
        if source_id in sources
    ]
    if len(matches) != 1:
        raise ValueError(f"unclassified training source: {source_id}")
    return matches[0]


def stable_order(row: dict[str, str]) -> str:
    identity = "|".join(
        (
            row["instrum"],
            row["source_id"],
            row["composition_id"],
            row["sha256"],
        )
    )
    return hashlib.sha256(identity.encode()).hexdigest()


def round_robin_sources(
    rows: list[dict[str, str]],
    limit: int,
) -> list[dict[str, str]]:
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_source[row["source_id"]].append(row)
    for source_rows in by_source.values():
        source_rows.sort(key=stable_order, reverse=True)

    selected: list[dict[str, str]] = []
    source_ids = sorted(by_source)
    while len(selected) < limit:
        progressed = False
        for source_id in source_ids:
            if by_source[source_id]:
                selected.append(by_source[source_id].pop())
                progressed = True
                if len(selected) == limit:
                    break
        if not progressed:
            break
    return selected


def balance_label(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_group[source_group(row["source_id"])].append(row)
    nonempty = {group: values for group, values in by_group.items() if values}
    if len(nonempty) < 2:
        raise ValueError("a balanced label requires at least two source groups")
    per_group = min(len(values) for values in nonempty.values())
    selected = []
    for group in sorted(nonempty):
        selected.extend(round_robin_sources(nonempty[group], per_group))
    return sorted(selected, key=stable_order)


def digest(rows: list[dict[str, str]]) -> str:
    payload = "\n".join(
        ",".join(
            (
                row["instrum"],
                row["path"],
                row["sha256"],
                row["source_id"],
                row["composition_id"],
            )
        )
        for row in rows
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def main() -> int:
    args = parse_args()
    input_root = args.input_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "1.0",
        "method": "equal-source-group-with-round-robin-sources",
        "source_groups": {
            group: sorted(sources)
            for group, sources in SOURCE_GROUPS.items()
        },
        "families": {},
    }

    for family in FAMILIES:
        with (input_root / f"{family}.csv").open(
            encoding="utf-8",
            newline="",
        ) as handle:
            rows = list(csv.DictReader(handle))
        selected = []
        label_reports = {}
        for label in (family, "other"):
            label_rows = [row for row in rows if row["instrum"] == label]
            balanced = balance_label(label_rows)
            selected.extend(balanced)
            label_reports[label] = {
                "input_count": len(label_rows),
                "selected_count": len(balanced),
                "source_counts": {
                    source_id: sum(
                        row["source_id"] == source_id
                        for row in balanced
                    )
                    for source_id in sorted(
                        {row["source_id"] for row in balanced}
                    )
                },
                "source_group_counts": {
                    group: sum(
                        source_group(row["source_id"]) == group
                        for row in balanced
                    )
                    for group in sorted(
                        {
                            source_group(row["source_id"])
                            for row in balanced
                        }
                    )
                },
            }
        selected.sort(
            key=lambda row: (
                row["instrum"],
                stable_order(row),
            )
        )
        output_path = output_root / f"{family}.csv"
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(selected[0]))
            writer.writeheader()
            writer.writerows(selected)
        report["families"][family] = {
            "path": str(output_path.relative_to(ROOT)),
            "row_count": len(selected),
            "sha256": digest(selected),
            "labels": label_reports,
        }

    (output_root / "index.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

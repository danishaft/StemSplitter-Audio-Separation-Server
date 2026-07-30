from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.training_data_registry import (  # noqa: E402
    load_training_data_registry,
)
from splitter.specialist_training_contract import (  # noqa: E402
    SPECIALIST_BASE_IDS,
)

STATUS_PATH = ROOT / "datasets" / "status" / "training-data-status.json"
OUTPUT_PATH = (
    ROOT / "datasets" / "status" / "specialist-corpus-gates.json"
)
PROFILE_PATHS = {
    "research_all": (
        ROOT
        / "datasets"
        / "corpora"
        / "research_all"
        / "specialist-sources-v1.json"
    ),
    "release_eligible": (
        ROOT
        / "datasets"
        / "corpora"
        / "release_eligible"
        / "specialist-sources-v1.json"
    ),
}
FAMILIES = SPECIALIST_BASE_IDS
SPLITS = ("train", "validation", "test")
SYNTHETIC_OR_AUGMENTATION_SOURCES = {
    "cocochorales",
    "nsynth",
    "slakh2100",
    "tinysol",
    "vsco_community",
}
THRESHOLDS = {
    "target_active_training_hours": 20.0,
    "independent_training_compositions": 200,
    "real_training_active_hours": 10.0,
    "real_training_projects": 30,
    "validation_real_songs": 15,
    "test_real_songs": 15,
    "heldout_real_songs": 30,
    "split_leakage_compositions": 0,
}


def _active_seconds(row: dict[str, Any]) -> float:
    audio = row["audio"]
    return float(audio["duration_seconds"]) * float(audio["active_fraction"])


def _exposure_seconds(row: dict[str, Any]) -> float:
    return float(row["audio"]["duration_seconds"])


def _load_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (ROOT / "datasets" / "manifests" / "items").glob(
            "**/items.jsonl"
        )
    ):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if (
                row.get("accepted") is True
                and row.get("item_role") == "target"
                and row.get("family") in FAMILIES
            ):
                rows.append(row)
    deduplicated: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["source_id"]), str(row["audio"]["sha256"]))
        prior = deduplicated.get(key)
        if prior is not None and prior.get("split") != row.get("split"):
            raise RuntimeError(
                f"duplicate audio crosses splits: {key[0]}:{key[1]}"
            )
        deduplicated[key] = row
    return list(deduplicated.values())


def _recoverable_sources(status: dict[str, Any]) -> set[str]:
    return {
        source_id
        for source_id, source in status["sources"].items()
        if (
            int(source.get("available_file_count") or 0) > 0
            or int(source.get("selected_subset_count") or 0) > 0
        )
    }


def _profile_sources(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return set(payload["selected_source_ids"])


def _group_active_seconds(
    rows: list[dict[str, Any]],
    registry: Any,
) -> float:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (str(row["source_id"]), str(row["composition_id"]))
        ].append(row)
    total = 0.0
    for (source_id, _), group in grouped.items():
        acquisition = registry.sources[source_id].raw.get("acquisition") or {}
        values = [_active_seconds(row) for row in group]
        if acquisition.get("group_duration_policy") == (
            "synchronized_views_mean"
        ):
            total += sum(values) / len(values)
        else:
            total += sum(values)
    return total


def _real_project_count(
    rows: list[dict[str, Any]],
    registry: Any,
) -> int:
    rows_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_source[str(row["source_id"])].append(row)
    total = 0
    for source_id, source_rows in rows_by_source.items():
        acquisition = registry.sources[source_id].raw.get("acquisition") or {}
        override = acquisition.get("independent_project_count")
        if override is not None:
            total += min(
                int(override),
                len(
                    {
                        str(row["composition_id"])
                        for row in source_rows
                    }
                ),
            )
        else:
            total += len(
                {str(row["composition_id"]) for row in source_rows}
            )
    return total


def _family_report(
    rows: list[dict[str, Any]],
    family: str,
    registry: Any,
) -> dict[str, Any]:
    family_rows = [
        row
        for row in rows
        if row["family"] == family and row.get("item_role") == "target"
    ]
    real_rows = [
        row
        for row in family_rows
        if row["source_id"] not in SYNTHETIC_OR_AUGMENTATION_SOURCES
    ]
    split_reports: dict[str, dict[str, Any]] = {}
    for split in SPLITS:
        split_rows = [
            row for row in family_rows if row.get("split") == split
        ]
        split_real = [
            row for row in real_rows if row.get("split") == split
        ]
        split_reports[split] = {
            "file_count": len(split_rows),
            "composition_count": len(
                {str(row["composition_id"]) for row in split_rows}
            ),
            "real_composition_count": len(
                {str(row["composition_id"]) for row in split_real}
            ),
            "target_exposure_hours": sum(
                _exposure_seconds(row) for row in split_rows
            )
            / 3600,
            "target_active_hours": _group_active_seconds(
                split_rows,
                registry,
            )
            / 3600,
            "real_target_active_hours": _group_active_seconds(
                split_real,
                registry,
            )
            / 3600,
        }

    composition_splits: dict[str, set[str]] = defaultdict(set)
    for row in family_rows:
        composition_splits[str(row["composition_id"])].add(str(row["split"]))
    leakage_count = sum(
        len(splits) > 1 for splits in composition_splits.values()
    )
    validation_real = split_reports["validation"]["real_composition_count"]
    test_real = split_reports["test"]["real_composition_count"]
    actual = {
        "target_active_training_hours": split_reports["train"][
            "target_active_hours"
        ],
        "independent_training_compositions": split_reports["train"][
            "composition_count"
        ],
        "real_training_active_hours": split_reports["train"][
            "real_target_active_hours"
        ],
        "real_training_projects": split_reports["train"][
            "real_composition_count"
        ],
        "validation_real_songs": validation_real,
        "test_real_songs": test_real,
        "heldout_real_songs": validation_real + test_real,
        "split_leakage_compositions": leakage_count,
    }
    actual["real_training_projects"] = _real_project_count(
        [row for row in real_rows if row.get("split") == "train"],
        registry,
    )
    gates = {
        name: {
            "actual": value,
            "required": THRESHOLDS[name],
            "passed": (
                value == requirement
                if name == "split_leakage_compositions"
                else value >= requirement
            ),
        }
        for name, value in actual.items()
        for requirement in [THRESHOLDS[name]]
    }
    return {
        "ready_for_scaling_pilots": all(
            gate["passed"] for gate in gates.values()
        ),
        "sources": sorted({str(row["source_id"]) for row in family_rows}),
        "splits": split_reports,
        "gates": gates,
    }


def main() -> int:
    registry = load_training_data_registry()
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    recoverable = _recoverable_sources(status)
    all_rows = _load_rows()
    profiles: dict[str, Any] = {}
    for profile, profile_path in PROFILE_PATHS.items():
        selected_sources = _profile_sources(profile_path)
        included_sources = selected_sources & recoverable
        rows = [
            row
            for row in all_rows
            if str(row["source_id"]) in included_sources
        ]
        profiles[profile] = {
            "selected_sources": sorted(selected_sources),
            "recoverable_sources": sorted(included_sources),
            "audited_but_unrecoverable_sources": sorted(
                {
                    str(row["source_id"])
                    for row in all_rows
                    if str(row["source_id"]) in selected_sources
                    and str(row["source_id"]) not in recoverable
                }
            ),
            "families": {
                family: _family_report(rows, family, registry)
                for family in FAMILIES
            },
        }
    payload = {
        "schema_version": "1.0",
        "thresholds": THRESHOLDS,
        "profiles": profiles,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH.relative_to(ROOT)),
                "profiles": {
                    profile: {
                        family: report["ready_for_scaling_pilots"]
                        for family, report in value["families"].items()
                    }
                    for profile, value in profiles.items()
                },
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

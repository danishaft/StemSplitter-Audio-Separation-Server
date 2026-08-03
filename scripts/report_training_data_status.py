from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.training_data_registry import load_training_data_registry  # noqa: E402

INVENTORY_ROOT = ROOT / "datasets" / "inventories"
RECEIPT_ROOT = ROOT / "datasets" / "manifests" / "acquisition"
ITEM_MANIFEST_ROOT = ROOT / "datasets" / "manifests" / "items"
DEFAULT_OUTPUT = ROOT / "datasets" / "status" / "training-data-status.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report real specialist training-data acquisition progress."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_training_data_registry()
    sources: dict[str, object] = {}
    totals: Counter[str] = Counter()

    for source in registry.sources.values():
        acquisition = source.raw.get("acquisition") or {}
        provider = str(acquisition.get("provider") or "unconfigured")
        inventory_path = (
            INVENTORY_ROOT / source.source_id / source.version / "inventory.json"
        )
        inventory = _read_json(inventory_path)
        provider_files = {
            str(row["path"]): row
            for row in inventory.get("files") or []
        }
        receipts = _load_receipts(source.source_id, source.version)
        selections = _load_selections(source.source_id, source.version)
        local_receipts = [
            receipt for receipt in receipts if _local_receipt_is_available(receipt)
        ]
        remote_receipts = [
            receipt
            for receipt in receipts
            if (
                isinstance(receipt.get("object"), dict)
                and receipt.get("remote_readback_verified") is True
            )
        ]
        unverified_remote_receipts = [
            receipt
            for receipt in receipts
            if (
                isinstance(receipt.get("object"), dict)
                and receipt.get("remote_readback_verified") is not True
            )
        ]
        available_receipts = {
            str(receipt["provider_path"]): receipt
            for receipt in [*remote_receipts, *local_receipts]
        }
        available_paths = set(available_receipts)
        available_bytes = sum(
            int(receipt.get("size_bytes") or 0)
            for receipt in available_receipts.values()
        )
        local_selections = [
            selection
            for selection in selections
            if _local_selection_is_available(selection)
        ]
        selection_config = acquisition.get("selection")
        required_selection_name = (
            str(selection_config.get("name") or "")
            if isinstance(selection_config, dict)
            else ""
        )
        selection_complete = any(
            str(selection.get("selection_name") or "")
            == required_selection_name
            for selection in local_selections
        )
        total_bytes = int(inventory.get("total_size_bytes") or 0)
        missing_paths = sorted(set(provider_files) - available_paths)
        audit_summary = _load_audit_summary(
            source.source_id,
            source.version,
            group_duration_policy=str(
                acquisition.get("group_duration_policy") or ""
            ),
        )
        if provider == "manual":
            status = "manual_access_required"
        elif not inventory:
            status = "inventory_pending"
        elif not provider_files:
            status = "provider_has_no_files"
        elif required_selection_name and selection_complete:
            status = "selected_subset_acquired"
        elif not missing_paths:
            status = "acquired"
        elif available_paths:
            status = "partially_acquired"
        elif unverified_remote_receipts:
            status = "remote_read_blocked"
        else:
            status = "inventory_ready"

        sources[source.source_id] = {
            "display_name": source.display_name,
            "version": source.version,
            "provider": provider,
            "status": status,
            "families": list(source.families),
            "inventory_file_count": len(provider_files),
            "inventory_bytes": total_bytes,
            "available_file_count": len(available_paths),
            "available_bytes": available_bytes,
            "local_retained_file_count": len(local_receipts),
            "local_retained_bytes": _receipt_bytes(local_receipts),
            "remote_verified_file_count": len(remote_receipts),
            "remote_verified_bytes": _receipt_bytes(remote_receipts),
            "remote_unverified_file_count": len(unverified_remote_receipts),
            "remote_unverified_bytes": _receipt_bytes(
                unverified_remote_receipts
            ),
            "selected_subset_count": len(local_selections),
            "selected_entry_count": sum(
                int(selection.get("entry_count") or 0)
                for selection in local_selections
            ),
            "selected_compressed_bytes": sum(
                int(selection.get("compressed_size_bytes") or 0)
                for selection in local_selections
            ),
            "selected_uncompressed_bytes": sum(
                int(selection.get("uncompressed_size_bytes") or 0)
                for selection in local_selections
            ),
            "remaining_file_count": len(missing_paths),
            "remaining_bytes": sum(
                int(provider_files[path].get("size_bytes") or 0)
                for path in missing_paths
            ),
            "missing_paths": missing_paths,
            "audit": audit_summary,
            **(
                {"manual_reason": str(acquisition.get("reason") or "")}
                if provider == "manual"
                else {}
            ),
        }
        totals["inventory_bytes"] += total_bytes
        totals["available_bytes"] += available_bytes
        totals["local_retained_bytes"] += _receipt_bytes(local_receipts)
        totals["remote_verified_bytes"] += _receipt_bytes(remote_receipts)
        totals["remote_unverified_bytes"] += _receipt_bytes(
            unverified_remote_receipts
        )
        totals["inventory_file_count"] += len(provider_files)
        totals["available_file_count"] += len(available_paths)
        totals["local_retained_file_count"] += len(local_receipts)
        totals["remote_verified_file_count"] += len(remote_receipts)
        totals["remote_unverified_file_count"] += len(
            unverified_remote_receipts
        )
        totals["selected_subset_count"] += len(local_selections)
        totals["selected_entry_count"] += sum(
            int(selection.get("entry_count") or 0)
            for selection in local_selections
        )
        totals["selected_compressed_bytes"] += sum(
            int(selection.get("compressed_size_bytes") or 0)
            for selection in local_selections
        )
        totals["selected_uncompressed_bytes"] += sum(
            int(selection.get("uncompressed_size_bytes") or 0)
            for selection in local_selections
        )
        totals[f"status:{status}"] += 1

    payload = {
        "schema_version": "1.0",
        "registry_sha256": registry.registry_sha256,
        "source_count": len(sources),
        "totals": dict(totals),
        "sources": sources,
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(output),
                "source_count": len(sources),
                "inventory_bytes": totals["inventory_bytes"],
                "available_bytes": totals["available_bytes"],
                "available_file_count": totals["available_file_count"],
                "remote_verified_file_count": totals[
                    "remote_verified_file_count"
                ],
                "remote_unverified_file_count": totals[
                    "remote_unverified_file_count"
                ],
                "selected_subset_count": totals["selected_subset_count"],
                "selected_entry_count": totals["selected_entry_count"],
            },
            sort_keys=True,
        )
    )
    return 0


def _load_receipts(source_id: str, version: str) -> list[dict[str, object]]:
    root = RECEIPT_ROOT / source_id / version
    if not root.exists():
        return []
    receipts = []
    for path in root.rglob("*.receipt.json"):
        payload = _read_json(path)
        if payload:
            receipts.append(payload)
    return receipts


def _load_selections(source_id: str, version: str) -> list[dict[str, object]]:
    root = RECEIPT_ROOT / source_id / version
    if not root.exists():
        return []
    selections = []
    for path in root.rglob("*.selection.json"):
        payload = _read_json(path)
        if payload:
            selections.append(payload)
    return selections


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _local_receipt_is_available(receipt: dict[str, object]) -> bool:
    if receipt.get("local_retained") is not True:
        return False
    local_path = receipt.get("local_path")
    if not isinstance(local_path, str) or not local_path:
        return False
    path = Path(local_path)
    if not path.is_absolute():
        path = ROOT / path
    return path.is_file() and path.stat().st_size == int(
        receipt.get("size_bytes") or -1
    )


def _receipt_bytes(receipts: list[dict[str, object]]) -> int:
    return sum(int(receipt.get("size_bytes") or 0) for receipt in receipts)


def _local_selection_is_available(selection: dict[str, object]) -> bool:
    if selection.get("local_retained") is not True:
        return False
    local_path = selection.get("local_path")
    if not isinstance(local_path, str) or not local_path:
        return False
    path = Path(local_path)
    if not path.is_absolute():
        path = ROOT / path
    return path.is_dir()


def _load_audit_summary(
    source_id: str,
    version: str,
    *,
    group_duration_policy: str,
) -> dict[str, object] | None:
    root = ITEM_MANIFEST_ROOT / source_id / version
    if not root.exists():
        return None
    rows: list[dict[str, object]] = []
    archive_count = 0
    for manifest_path in sorted(root.glob("*/items.jsonl")):
        archive_count += 1
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    if not rows:
        return None

    accepted = [row for row in rows if row.get("accepted") is True]
    accepted_targets = [
        row for row in accepted if row.get("item_role") == "target"
    ]
    accepted_hard_negatives = [
        row for row in accepted if row.get("item_role") == "hard_negative"
    ]
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in accepted:
        grouped.setdefault(str(row["composition_id"]), []).append(row)
    split_leakage = sum(
        len({str(row.get("split")) for row in group}) > 1
        for group in grouped.values()
    )

    def duration(row: dict[str, object]) -> float:
        audio = row.get("audio")
        return float(audio.get("duration_seconds") or 0) if isinstance(
            audio, dict
        ) else 0.0

    def active_duration(row: dict[str, object]) -> float:
        audio = row.get("audio")
        if not isinstance(audio, dict):
            return 0.0
        return float(audio.get("duration_seconds") or 0) * float(
            audio.get("active_fraction") or 0
        )

    summary: dict[str, object] = {
        "archive_count": archive_count,
        "audio_file_count": len(rows),
        "accepted_file_count": len(accepted),
        "rejected_file_count": len(rows) - len(accepted),
        "accepted_file_exposure_hours": sum(
            duration(row) for row in accepted
        )
        / 3600,
        "accepted_file_active_hours": sum(
            active_duration(row) for row in accepted
        )
        / 3600,
        "accepted_target_exposure_hours": sum(
            duration(row) for row in accepted_targets
        )
        / 3600,
        "accepted_target_active_hours": sum(
            active_duration(row) for row in accepted_targets
        )
        / 3600,
        "accepted_hard_negative_active_hours": sum(
            active_duration(row) for row in accepted_hard_negatives
        )
        / 3600,
        "independent_group_count": len(grouped),
        "split_leakage_group_count": split_leakage,
        "family_counts": dict(
            Counter(
                str(row["family"])
                for row in accepted
                if row.get("family") is not None
            )
        ),
        "split_counts": dict(
            Counter(str(row.get("split")) for row in accepted)
        ),
        "rejection_counts": dict(
            Counter(
                str(reason)
                for row in rows
                for reason in row.get("rejection_reasons") or []
            )
        ),
    }
    if group_duration_policy == "synchronized_views_mean":
        summary["independent_group_timeline_hours"] = sum(
            sum(duration(row) for row in group) / len(group)
            for group in grouped.values()
        ) / 3600
        summary["independent_group_active_hours"] = sum(
            sum(active_duration(row) for row in group) / len(group)
            for group in grouped.values()
        ) / 3600
        summary["group_duration_policy"] = group_duration_policy
    return summary


if __name__ == "__main__":
    raise SystemExit(main())

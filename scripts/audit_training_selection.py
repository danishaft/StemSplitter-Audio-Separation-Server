from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.training_corpus import (  # noqa: E402
    TrainingCorpusError,
    audit_training_tree,
    file_checksum,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit a verified selective training-data extraction."
    )
    parser.add_argument("source_id")
    parser.add_argument("receipt", type=Path)
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Audit only newly selected files and reuse unchanged item rows.",
    )
    return parser.parse_args()


def _write_rows(
    rows: list[dict[str, object]],
    output_dir: Path,
    *,
    source_id: str,
    source_version: str,
    provenance_sha256: str,
) -> dict[str, object]:
    rows.sort(key=lambda row: str(row["relative_path"]))
    seen_hashes: dict[str, str] = {}
    for row in rows:
        row["provenance_sha256"] = provenance_sha256
        if not row.get("accepted"):
            continue
        audio = row.get("audio")
        if not isinstance(audio, dict):
            continue
        audio_hash = str(audio.get("sha256") or "")
        duplicate_of = seen_hashes.get(audio_hash)
        if duplicate_of is None:
            seen_hashes[audio_hash] = str(row["relative_path"])
            continue
        row["accepted"] = False
        row["duplicate_of"] = duplicate_of
        reasons = set(row.get("rejection_reasons") or [])
        reasons.add("duplicate_audio")
        row["rejection_reasons"] = sorted(reasons)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "items.jsonl"
    temporary_manifest = manifest_path.with_suffix(".jsonl.tmp")
    with temporary_manifest.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    os.replace(temporary_manifest, manifest_path)

    accepted = [row for row in rows if row.get("accepted") is True]
    report: dict[str, object] = {
        "schema_version": "1.0",
        "source_id": source_id,
        "source_version": source_version,
        "provenance_sha256": provenance_sha256,
        "manifest": str(manifest_path.relative_to(ROOT)),
        "audio_file_count": len(rows),
        "accepted_file_count": len(accepted),
        "rejected_file_count": len(rows) - len(accepted),
        "accepted_duration_seconds": sum(
            float(row["audio"]["duration_seconds"]) for row in accepted
        ),
        "accepted_active_seconds": sum(
            float(row["audio"]["duration_seconds"])
            * float(row["audio"]["active_fraction"])
            for row in accepted
        ),
        "accepted_target_active_seconds": sum(
            float(row["audio"]["duration_seconds"])
            * float(row["audio"]["active_fraction"])
            for row in accepted
            if row.get("item_role") == "target"
        ),
        "accepted_composition_count": len(
            {str(row["composition_id"]) for row in accepted}
        ),
        "family_counts": dict(
            Counter(
                str(row["family"])
                for row in accepted
                if row.get("family") is not None
            )
        ),
        "hard_negative_count": sum(
            row.get("item_role") == "hard_negative" for row in accepted
        ),
        "split_counts": dict(
            Counter(str(row["split"]) for row in accepted)
        ),
        "composition_split_counts": dict(
            Counter(
                {
                    str(row["composition_id"]): str(row["split"])
                    for row in accepted
                }.values()
            )
        ),
        "rejection_counts": dict(
            Counter(
                str(reason)
                for row in rows
                for reason in row.get("rejection_reasons") or []
            )
        ),
    }
    report_path = output_dir / "report.json"
    temporary_report = report_path.with_suffix(".json.tmp")
    temporary_report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_report, report_path)
    return report


def _incremental_audit(
    source_id: str,
    receipt: dict[str, object],
    receipt_path: Path,
    local_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    manifest_reference = str(receipt.get("selection_manifest") or "")
    manifest_path = Path(manifest_reference)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    selection = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected_paths = {
        str(path)
        for archive in selection["archives"]
        for path in archive["paths"]
    }
    existing_path = output_dir / "items.jsonl"
    existing_rows = (
        [
            json.loads(line)
            for line in existing_path.read_text(encoding="utf-8").splitlines()
        ]
        if existing_path.is_file()
        else []
    )
    reusable = {
        str(row["relative_path"]): row
        for row in existing_rows
        if (
            str(row["relative_path"]) in selected_paths
            and (local_path / str(row["relative_path"])).is_file()
        )
    }
    split_assignments = receipt.get("song_split_assignments")
    if not isinstance(split_assignments, dict):
        raise TrainingCorpusError(
            "incremental audit requires frozen song split assignments"
        )

    def apply_current_split(row: dict[str, object]) -> None:
        composition_id = str(row["composition_id"])
        relative_path = str(row["relative_path"])
        row["local_path"] = str(local_path / relative_path)
        song_id = composition_id.removeprefix(f"{source_id}:")
        split = split_assignments.get(
            composition_id,
            split_assignments.get(song_id),
        )
        if split not in {"train", "validation", "test"}:
            raise TrainingCorpusError(
                f"missing split assignment: {composition_id}"
            )
        row["split"] = split

    for row in reusable.values():
        apply_current_split(row)
    new_paths = sorted(selected_paths - reusable.keys())
    if not new_paths:
        return _write_rows(
            list(reusable.values()),
            output_dir,
            source_id=source_id,
            source_version=str(receipt["source_version"]),
            provenance_sha256=file_checksum(receipt_path),
        )

    incremental_root = local_path.parent / ".incremental-audit"
    incremental_output = output_dir.parent / f".{output_dir.name}.incremental"
    if incremental_root.exists():
        shutil.rmtree(incremental_root)
    if incremental_output.exists():
        shutil.rmtree(incremental_output)
    incremental_root.mkdir()
    try:
        for relative_path in new_paths:
            source = local_path / relative_path
            if not source.is_file():
                raise TrainingCorpusError(
                    f"selected file is missing: {relative_path}"
                )
            destination = incremental_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(source, destination)
        audit_training_tree(
            source_id,
            incremental_root,
            output_dir=incremental_output,
            provenance_sha256=file_checksum(receipt_path),
            split_assignments=receipt.get("song_split_assignments"),
        )
        new_rows = [
            json.loads(line)
            for line in (incremental_output / "items.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        for row in new_rows:
            relative_path = str(row["relative_path"])
            row["local_path"] = str(local_path / relative_path)
            apply_current_split(row)
        combined = list(reusable.values()) + new_rows
        if {str(row["relative_path"]) for row in combined} != selected_paths:
            raise TrainingCorpusError(
                "incremental audit did not cover the frozen selection"
            )
        return _write_rows(
            combined,
            output_dir,
            source_id=source_id,
            source_version=str(receipt["source_version"]),
            provenance_sha256=file_checksum(receipt_path),
        )
    finally:
        shutil.rmtree(incremental_root, ignore_errors=True)
        shutil.rmtree(incremental_output, ignore_errors=True)


def main() -> int:
    args = parse_args()
    receipt_path = args.receipt.expanduser().resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if str(receipt.get("source_id") or "") != args.source_id:
        print("training selection source mismatch", file=sys.stderr)
        return 1
    local_path = Path(str(receipt.get("local_path") or ""))
    if not local_path.is_absolute():
        local_path = ROOT / local_path
    if not local_path.is_dir():
        print("training selection is not available locally", file=sys.stderr)
        return 1
    selection_name = str(receipt.get("selection_name") or "selection")
    version = str(receipt.get("source_version") or "unknown")
    output_dir = (
        ROOT
        / "datasets"
        / "manifests"
        / "items"
        / args.source_id
        / version
        / selection_name
    )
    try:
        split_assignments = receipt.get("song_split_assignments")
        if split_assignments is not None and not isinstance(
            split_assignments,
            dict,
        ):
            print(
                "training selection split assignments are invalid",
                file=sys.stderr,
            )
            return 1
        if args.reuse_existing:
            report = _incremental_audit(
                args.source_id,
                receipt,
                receipt_path,
                local_path,
                output_dir,
            )
        else:
            report = audit_training_tree(
                args.source_id,
                local_path,
                output_dir=output_dir,
                provenance_sha256=file_checksum(receipt_path),
                split_assignments=split_assignments,
            )
    except TrainingCorpusError as exc:
        print(f"training selection audit failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

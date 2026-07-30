from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.training_data_acquisition import (  # noqa: E402
    TrainingDataAcquisitionError,
    acquire_remote_zip_manifest,
    acquire_remote_zip_selection,
    acquire_source_file,
    snapshot_remote_zip_inventory,
    snapshot_source_inventory,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inventory or acquire one immutable training-data source."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory")
    inventory.add_argument("source_id")

    inspect_zip = subparsers.add_parser("inspect-zip")
    inspect_zip.add_argument("source_id")
    inspect_zip.add_argument("file_path")

    select_zip = subparsers.add_parser("acquire-zip-selection")
    select_zip.add_argument("source_id")
    select_zip.add_argument("file_path")
    select_zip.add_argument("selection_name")
    select_zip.add_argument(
        "--include-component",
        action="append",
        default=[],
    )
    select_zip.add_argument(
        "--suffix",
        action="append",
        default=[".wav"],
    )

    select_manifest = subparsers.add_parser("acquire-zip-manifest")
    select_manifest.add_argument("manifest", type=Path)
    select_manifest.add_argument("--validate-only", action="store_true")

    acquire = subparsers.add_parser("acquire")
    acquire.add_argument("source_id")
    acquire.add_argument("file_path")
    acquire.add_argument("--upload", action="store_true")
    acquire.add_argument("--delete-after-upload", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "inventory":
            path, payload = snapshot_source_inventory(args.source_id)
            print(
                json.dumps(
                    {
                        "inventory": str(path),
                        "file_count": payload["file_count"],
                        "total_size_bytes": payload["total_size_bytes"],
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "inspect-zip":
            path, payload = snapshot_remote_zip_inventory(
                args.source_id,
                args.file_path,
            )
            print(
                json.dumps(
                    {
                        "inventory": str(path),
                        "entry_count": payload["entry_count"],
                        "compressed_size_bytes": payload[
                            "compressed_size_bytes"
                        ],
                        "uncompressed_size_bytes": payload[
                            "uncompressed_size_bytes"
                        ],
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "acquire-zip-selection":
            target_root, receipt = acquire_remote_zip_selection(
                args.source_id,
                args.file_path,
                args.selection_name,
                include_components=tuple(args.include_component),
                suffixes=tuple(args.suffix),
            )
            print(
                json.dumps(
                    {
                        "source_id": args.source_id,
                        "selection_name": receipt["selection_name"],
                        "local_path": str(target_root),
                        "entry_count": receipt["entry_count"],
                        "compressed_size_bytes": receipt[
                            "compressed_size_bytes"
                        ],
                        "uncompressed_size_bytes": receipt[
                            "uncompressed_size_bytes"
                        ],
                    },
                    sort_keys=True,
                )
            )
            return 0

        if args.command == "acquire-zip-manifest":
            target_root, receipt = acquire_remote_zip_manifest(
                args.manifest,
                validate_only=args.validate_only,
            )
            print(
                json.dumps(
                    {
                        "source_id": receipt["source_id"],
                        "selection_name": receipt["selection_name"],
                        "local_path": str(target_root),
                        "entry_count": receipt["entry_count"],
                        "compressed_size_bytes": receipt[
                            "compressed_size_bytes"
                        ],
                        "uncompressed_size_bytes": receipt[
                            "uncompressed_size_bytes"
                        ],
                        "validated": receipt.get("validated", True),
                    },
                    sort_keys=True,
                )
            )
            return 0

        local_path, receipt = acquire_source_file(
            args.source_id,
            args.file_path,
            upload=args.upload,
            delete_after_upload=args.delete_after_upload,
        )
        print(
            json.dumps(
                {
                    "source_id": args.source_id,
                    "provider_path": args.file_path,
                    "local_path": str(local_path) if local_path else None,
                    "size_bytes": receipt["size_bytes"],
                    "sha256": receipt["sha256"],
                    "object": receipt["object"],
                },
                sort_keys=True,
            )
        )
        return 0
    except TrainingDataAcquisitionError as exc:
        print(f"training-data acquisition failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

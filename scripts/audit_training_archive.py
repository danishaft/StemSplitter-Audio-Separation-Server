from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.training_corpus import (  # noqa: E402
    TrainingCorpusError,
    audit_training_tree,
    extract_archive_safely,
    file_checksum,
    restore_archive_from_receipt,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore, safely extract, and audit one training archive."
    )
    parser.add_argument("source_id")
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--cleanup", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt_path = args.receipt.expanduser().resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    provider_path = str(receipt["provider_path"])
    version = str(receipt["source_version"])
    safe_name = Path(provider_path).name
    staging_root = ROOT / "datasets" / "staging" / args.source_id / version
    archive_path = staging_root / safe_name
    extracted_path = (
        ROOT
        / "datasets"
        / "extracted"
        / args.source_id
        / version
        / safe_name.replace(".", "-")
    )
    output_dir = (
        ROOT
        / "datasets"
        / "manifests"
        / "items"
        / args.source_id
        / version
        / safe_name.replace(".", "-")
    )

    try:
        if not archive_path.exists():
            restore_archive_from_receipt(receipt_path, archive_path)
        archive_sha256 = file_checksum(archive_path)
        extract_archive_safely(archive_path, extracted_path)
        report = audit_training_tree(
            args.source_id,
            extracted_path,
            output_dir=output_dir,
            archive_sha256=archive_sha256,
        )
        if args.cleanup:
            if receipt.get("remote_readback_verified") is not True:
                raise TrainingCorpusError(
                    "cleanup refused: archive has no verified remote read-back"
                )
            archive_path.unlink(missing_ok=True)
            shutil.rmtree(extracted_path, ignore_errors=True)
            receipt["local_path"] = None
            receipt["local_retained"] = False
            receipt_path.write_text(
                json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(report, sort_keys=True))
        return 0
    except TrainingCorpusError as exc:
        print(f"training archive audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

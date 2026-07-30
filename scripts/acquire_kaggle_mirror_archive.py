from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.training_corpus import TrainingCorpusError, file_checksum  # noqa: E402
from splitter.training_data_registry import (  # noqa: E402
    load_training_data_registry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Acquire an exact archive from a public Kaggle mirror and verify it "
            "against the authoritative provider's size and checksum."
        )
    )
    parser.add_argument("source_id")
    return parser.parse_args()


def _required_mapping(
    value: object,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TrainingCorpusError(f"{field} must be a mapping")
    return value


def _required_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise TrainingCorpusError(f"{field} is required")
    return text


def _resolved_kaggle_version(
    target_root: Path,
    owner: str,
    dataset: str,
    provider_path: str,
) -> str:
    marker_root = (
        target_root / ".complete" / "datasets" / owner / dataset
    )
    markers = sorted(marker_root.glob(f"*/{provider_path}.complete"))
    if len(markers) != 1:
        raise TrainingCorpusError(
            "could not resolve exactly one Kaggle dataset version marker"
        )
    return markers[0].relative_to(marker_root).parts[0]


def main() -> int:
    args = parse_args()
    registry = load_training_data_registry()
    source = registry.sources.get(args.source_id)
    if source is None:
        print(f"unknown training source: {args.source_id}", file=sys.stderr)
        return 1

    try:
        acquisition = _required_mapping(
            source.raw.get("acquisition"),
            "source acquisition",
        )
        mirror = _required_mapping(
            acquisition.get("verified_archive_mirror"),
            "verified_archive_mirror",
        )
        handle = _required_text(mirror.get("handle"), "mirror handle")
        provider_path = _required_text(
            mirror.get("provider_path"),
            "mirror provider_path",
        )
        expected_size = int(mirror.get("authoritative_size_bytes") or 0)
        expected_algorithm = _required_text(
            mirror.get("authoritative_checksum_algorithm"),
            "authoritative_checksum_algorithm",
        ).lower()
        expected_checksum = _required_text(
            mirror.get("authoritative_checksum"),
            "authoritative_checksum",
        ).lower()
        if expected_size <= 0:
            raise TrainingCorpusError(
                "authoritative_size_bytes must be positive"
            )
        if expected_algorithm not in {"md5", "sha256"}:
            raise TrainingCorpusError(
                "authoritative checksum must be md5 or sha256"
            )

        try:
            import kagglehub
        except ImportError as exc:
            raise TrainingCorpusError("kagglehub_not_installed") from exc

        owner, dataset, *handle_suffix = handle.split("/")
        if len(handle_suffix) not in {0, 2}:
            raise TrainingCorpusError(
                "Kaggle handle must be owner/dataset or "
                "owner/dataset/versions/N"
            )
        if handle_suffix and handle_suffix[0] != "versions":
            raise TrainingCorpusError("invalid versioned Kaggle handle")

        target_root = (
            ROOT
            / "datasets"
            / "staging"
            / source.source_id
            / source.version
            / "mirror-archives"
        )
        downloaded = Path(
            kagglehub.dataset_download(
                handle,
                path=provider_path,
                output_dir=str(target_root),
            )
        ).resolve()
        if downloaded != (target_root / provider_path).resolve():
            raise TrainingCorpusError(
                f"unexpected Kaggle download path: {downloaded}"
            )
        if downloaded.stat().st_size != expected_size:
            raise TrainingCorpusError(
                "mirror archive size does not match the authoritative archive"
            )
        if file_checksum(downloaded, expected_algorithm) != expected_checksum:
            raise TrainingCorpusError(
                "mirror archive checksum does not match the authoritative archive"
            )

        version = (
            handle_suffix[1]
            if handle_suffix
            else _resolved_kaggle_version(
                target_root,
                owner,
                dataset,
                provider_path,
            )
        )
        sha256 = file_checksum(downloaded, "sha256")
        receipt = {
            "schema_version": "1.0",
            "source_id": source.source_id,
            "source_version": source.version,
            "provider": "kaggle_public_verified_mirror",
            "provider_path": provider_path,
            "provider_revision": f"{owner}/{dataset}/versions/{version}",
            "provider_checksum_algorithm": expected_algorithm,
            "provider_checksum": expected_checksum,
            "authoritative_source_url": source.source_url,
            "mirror_source_url": (
                f"https://www.kaggle.com/datasets/{owner}/{dataset}"
            ),
            "size_bytes": expected_size,
            "sha256": sha256,
            "local_path": str(downloaded.relative_to(ROOT)),
            "local_retained": True,
            "rights_status": source.rights_status,
            "release_use": source.release_use,
        }
        receipt_payload = json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        receipt["receipt_sha256"] = hashlib.sha256(receipt_payload).hexdigest()
        receipt_path = (
            ROOT
            / "datasets"
            / "manifests"
            / "acquisition"
            / source.source_id
            / source.version
            / "verified-kaggle-mirror.receipt.json"
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, TrainingCorpusError) as exc:
        print(f"Kaggle mirror acquisition failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "local_path": str(downloaded),
                "provider_revision": receipt["provider_revision"],
                "sha256": sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

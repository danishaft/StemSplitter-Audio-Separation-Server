from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from splitter.training_corpus import (  # noqa: E402
    TrainingCorpusError,
    extract_archives_safely,
    file_checksum,
)
from splitter.training_data_registry import (  # noqa: E402
    load_training_data_registry,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize verified source-file receipts into one auditable corpus."
        )
    )
    parser.add_argument("source_id")
    parser.add_argument("selection_name")
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument("--audio-only", action="store_true")
    parser.add_argument("--transcode-wav-to-flac", action="store_true")
    parser.add_argument("--delete-archives-after", action="store_true")
    return parser.parse_args()


def _load_verified_receipt(
    path: Path,
    source_id: str,
    source_version: str,
) -> tuple[dict[str, Any], Path]:
    receipt_path = path.expanduser().resolve()
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if payload.get("source_id") != source_id:
        raise TrainingCorpusError(f"receipt source mismatch: {receipt_path}")
    if payload.get("source_version") != source_version:
        raise TrainingCorpusError(f"receipt version mismatch: {receipt_path}")
    local_path = Path(str(payload.get("local_path") or ""))
    if not local_path.is_absolute():
        local_path = ROOT / local_path
    if not local_path.is_file():
        raise TrainingCorpusError(f"receipt archive is unavailable: {local_path}")
    if local_path.stat().st_size != int(payload.get("size_bytes") or -1):
        raise TrainingCorpusError(f"receipt archive size mismatch: {local_path}")
    if file_checksum(local_path) != str(payload.get("sha256") or ""):
        raise TrainingCorpusError(f"receipt archive checksum mismatch: {local_path}")
    return payload, local_path


def _transcode_wav_to_flac(path: Path) -> None:
    if path.suffix.lower() != ".wav":
        return
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise TrainingCorpusError("ffmpeg is required for WAV-to-FLAC")
    output_path = path.with_suffix(".flac")
    if output_path.exists():
        raise TrainingCorpusError(
            f"transcoded archive member already exists: {output_path}"
        )
    result = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-map_metadata",
            "-1",
            "-compression_level",
            "8",
            str(output_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0 or not output_path.is_file():
        output_path.unlink(missing_ok=True)
        reason = result.stderr.strip() or "unknown ffmpeg error"
        raise TrainingCorpusError(f"WAV-to-FLAC failed for {path}: {reason}")
    path.unlink()


def main() -> int:
    args = parse_args()
    registry = load_training_data_registry()
    source = registry.sources.get(args.source_id)
    if source is None:
        print(f"unknown training source: {args.source_id}", file=sys.stderr)
        return 1

    try:
        if args.transcode_wav_to_flac and not args.audio_only:
            raise TrainingCorpusError(
                "--transcode-wav-to-flac requires --audio-only"
            )
        loaded = [
            _load_verified_receipt(path, source.source_id, source.version)
            for path in args.receipts
        ]
        provider_paths = [str(payload["provider_path"]) for payload, _ in loaded]
        if len(provider_paths) != len(set(provider_paths)):
            raise TrainingCorpusError("duplicate provider receipts in bundle")

        archives = [archive for _, archive in loaded]
        target_root = (
            ROOT
            / "datasets"
            / "staging"
            / source.source_id
            / source.version
            / "selections"
            / args.selection_name
        )
        member_filter = None
        if args.audio_only:
            def audio_member_filter(path: PurePosixPath) -> bool:
                return path.suffix.lower() in {
                    ".aif",
                    ".aiff",
                    ".flac",
                    ".mp3",
                    ".ogg",
                    ".wav",
                }

            member_filter = audio_member_filter
        extract_archives_safely(
            archives,
            target_root,
            member_filter=member_filter,
            postprocess_member=(
                _transcode_wav_to_flac
                if args.transcode_wav_to_flac
                else None
            ),
        )

        archive_records = [
            {
                "provider_path": payload["provider_path"],
                "provider_revision": payload.get("provider_revision"),
                "provider_checksum_algorithm": payload.get(
                    "provider_checksum_algorithm"
                ),
                "provider_checksum": payload.get("provider_checksum"),
                "size_bytes": payload["size_bytes"],
                "sha256": payload["sha256"],
            }
            for payload, _ in loaded
        ]
        provenance_payload = json.dumps(
            archive_records,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        receipt = {
            "schema_version": "1.0",
            "source_id": source.source_id,
            "source_version": source.version,
            "selection_name": args.selection_name,
            "provider_path": f"bundle:{args.selection_name}",
            "archives": archive_records,
            "archive_count": len(archive_records),
            "size_bytes": sum(
                int(record["size_bytes"]) for record in archive_records
            ),
            "provenance_sha256": hashlib.sha256(provenance_payload).hexdigest(),
            "entry_count": sum(1 for path in target_root.rglob("*") if path.is_file()),
            "materialization_filter": (
                "audio_only_flac_transcoded"
                if args.transcode_wav_to_flac
                else "audio_only"
                if args.audio_only
                else "all"
            ),
            "local_path": str(target_root.relative_to(ROOT)),
            "local_retained": True,
            "rights_status": source.rights_status,
            "release_use": source.release_use,
        }
        receipt_path = (
            ROOT
            / "datasets"
            / "manifests"
            / "acquisition"
            / source.source_id
            / source.version
            / f"{args.selection_name}.selection.json"
        )
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if args.delete_archives_after:
            for archive in archives:
                archive.unlink()
    except (OSError, json.JSONDecodeError, TrainingCorpusError) as exc:
        print(f"training bundle materialization failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "receipt": str(receipt_path),
                "local_path": str(target_root),
                "archive_count": receipt["archive_count"],
                "entry_count": receipt["entry_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

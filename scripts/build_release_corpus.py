#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import soundfile as sf


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from splitter.benchmark_corpus import load_and_validate_corpus
from splitter.ground_truth import build_babyslakh_references
from splitter.util import ensure_dir, file_sha256


DEFAULT_BABYSLAKH_ROOT = os.getenv("STEMSPLITTER_BABYSLAKH_ROOT")


def _duration(path: Path) -> float:
    return float(sf.info(path).duration)


def _excerpt(duration: float) -> tuple[float, float]:
    excerpt_duration = min(60.0, duration)
    return round(max(0.0, (duration - excerpt_duration) / 2.0), 3), round(
        excerpt_duration,
        3,
    )


def _song_id(prefix: str, path: Path) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in path.stem)
    return f"{prefix}-{slug.strip('-')}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the frozen 30-song release corpus.")
    parser.add_argument(
        "--babyslakh-root",
        type=Path,
        default=Path(DEFAULT_BABYSLAKH_ROOT) if DEFAULT_BABYSLAKH_ROOT else None,
    )
    parser.add_argument(
        "--listening-track",
        action="append",
        default=[],
        type=Path,
        help="Listening-only track; repeat exactly 20 times.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks" / "corpus" / "release-30-v1.json",
    )
    args = parser.parse_args()

    if args.babyslakh_root is None:
        parser.error("--babyslakh-root or STEMSPLITTER_BABYSLAKH_ROOT is required")
    if len(args.listening_track) != 20:
        parser.error("--listening-track must be provided exactly 20 times")

    babyslakh_root = args.babyslakh_root.expanduser().resolve()
    reference_root = ROOT / "benchmarks" / "ground_truth" / "release-30-v1"
    songs: list[dict[str, object]] = []
    for track_dir in sorted(babyslakh_root.glob("Track*"))[:10]:
        mix = track_dir / "mix.wav"
        duration = _duration(mix)
        excerpt_start, excerpt_duration = _excerpt(duration)
        song_id = f"babyslakh-{track_dir.name.lower()}"
        references = ensure_dir(reference_root / song_id / "references")
        build_babyslakh_references(track_dir, references)
        songs.append(
            {
                "id": song_id,
                "path": str(mix.resolve()),
                "sha256": file_sha256(mix),
                "duration_seconds": round(duration, 3),
                "excerpt_start_seconds": excerpt_start,
                "excerpt_duration_seconds": excerpt_duration,
                "difficulty": "easy",
                "genres": ["synthetic_multitrack"],
                "evidence_level": "ground_truth",
                "reference_root": str(references.resolve()),
                "license_status": "research_dataset",
            }
        )

    for path in args.listening_track:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise SystemExit(f"listening track is missing: {resolved}")
        duration = _duration(resolved)
        excerpt_start, excerpt_duration = _excerpt(duration)
        songs.append(
            {
                "id": _song_id("listening", resolved),
                "path": str(resolved),
                "sha256": file_sha256(resolved),
                "duration_seconds": round(duration, 3),
                "excerpt_start_seconds": excerpt_start,
                "excerpt_duration_seconds": excerpt_duration,
                "difficulty": "mixed",
                "genres": ["mixed_music"],
                "evidence_level": "blind_listening_only",
                "license_status": "reference_only_no_redistribution",
            }
        )

    payload = {
        "schema_version": 1,
        "corpus_id": "release-30-v1",
        "frozen_at": datetime.now(UTC).date().isoformat(),
        "purpose": "Eight-stem release qualification",
        "release_claim_eligible": True,
        "songs": songs,
    }
    output = args.output.expanduser().resolve()
    ensure_dir(output.parent)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _, validation = load_and_validate_corpus(output, verify_files=True)
    print(f"corpus={output}")
    print(f"songs={validation.song_count}")
    print(f"ground_truth={validation.ground_truth_count}")
    print(f"listening_only={validation.listening_only_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

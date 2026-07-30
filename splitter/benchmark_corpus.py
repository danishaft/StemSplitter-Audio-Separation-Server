from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .util import file_sha256


EVIDENCE_LEVELS = {"ground_truth", "blind_listening_only"}
LICENSE_STATUSES = {"research_dataset", "user_owned", "reference_only_no_redistribution"}
DIFFICULTIES = {"easy", "mixed", "hard", "failure_case"}


@dataclass(frozen=True)
class CorpusValidation:
    corpus_id: str
    song_count: int
    ground_truth_count: int
    listening_only_count: int
    total_excerpt_seconds: float
    release_claim_eligible: bool


def load_and_validate_corpus(path: Path, *, verify_files: bool = True) -> tuple[dict[str, Any], CorpusValidation]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("corpus_schema_version_must_be_1")
    corpus_id = str(payload.get("corpus_id") or "").strip()
    if not corpus_id:
        raise ValueError("corpus_id_required")
    songs = payload.get("songs")
    if not isinstance(songs, list) or not songs:
        raise ValueError("corpus_songs_required")

    ids: set[str] = set()
    ground_truth_count = 0
    total_excerpt_seconds = 0.0
    for index, song in enumerate(songs):
        if not isinstance(song, dict):
            raise ValueError(f"song_{index}_must_be_an_object")
        song_id = str(song.get("id") or "").strip()
        if not song_id or song_id in ids:
            raise ValueError(f"song_{index}_id_missing_or_duplicate")
        ids.add(song_id)
        if song.get("difficulty") not in DIFFICULTIES:
            raise ValueError(f"{song_id}_invalid_difficulty")
        if song.get("evidence_level") not in EVIDENCE_LEVELS:
            raise ValueError(f"{song_id}_invalid_evidence_level")
        if song.get("license_status") not in LICENSE_STATUSES:
            raise ValueError(f"{song_id}_invalid_license_status")
        if song.get("evidence_level") == "ground_truth":
            ground_truth_count += 1
            reference_root = Path(str(song.get("reference_root") or "")).expanduser()
            if verify_files and not reference_root.exists():
                raise ValueError(f"{song_id}_reference_root_missing")

        input_path = Path(str(song.get("path") or "")).expanduser()
        expected_hash = str(song.get("sha256") or "")
        duration = float(song.get("duration_seconds") or 0.0)
        excerpt_start = float(song.get("excerpt_start_seconds") or 0.0)
        excerpt_duration = float(song.get("excerpt_duration_seconds") or 0.0)
        if duration <= 0 or excerpt_duration <= 0 or excerpt_duration > 60:
            raise ValueError(f"{song_id}_invalid_duration")
        if excerpt_start < 0 or excerpt_start + excerpt_duration > duration:
            raise ValueError(f"{song_id}_excerpt_out_of_range")
        if not isinstance(song.get("genres"), list) or not song["genres"]:
            raise ValueError(f"{song_id}_genres_required")
        if verify_files:
            if not input_path.is_file():
                raise ValueError(f"{song_id}_input_missing")
            if not expected_hash or file_sha256(input_path) != expected_hash:
                raise ValueError(f"{song_id}_sha256_mismatch")
        total_excerpt_seconds += excerpt_duration

    release_claim_eligible = bool(payload.get("release_claim_eligible"))
    if release_claim_eligible and (len(songs) < 30 or ground_truth_count < 10):
        raise ValueError("release_claim_requires_30_songs_and_10_ground_truth_tracks")
    return payload, CorpusValidation(
        corpus_id=corpus_id,
        song_count=len(songs),
        ground_truth_count=ground_truth_count,
        listening_only_count=len(songs) - ground_truth_count,
        total_excerpt_seconds=round(total_excerpt_seconds, 3),
        release_claim_eligible=release_claim_eligible,
    )

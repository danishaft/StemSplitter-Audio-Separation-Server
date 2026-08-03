from __future__ import annotations

import json
from pathlib import Path

from splitter.benchmark_corpus import load_and_validate_corpus


def test_corpus_expands_environment_paths(monkeypatch, tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    monkeypatch.setenv("LOCAL_MEDIA_ROOT", str(media_root))
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_id": "portable-corpus",
                "release_claim_eligible": False,
                "songs": [
                    {
                        "id": "song-1",
                        "path": "${LOCAL_MEDIA_ROOT}/song.wav",
                        "sha256": "not-verified",
                        "duration_seconds": 30,
                        "excerpt_start_seconds": 0,
                        "excerpt_duration_seconds": 30,
                        "difficulty": "mixed",
                        "genres": ["test"],
                        "evidence_level": "blind_listening_only",
                        "license_status": "user_owned",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    payload, validation = load_and_validate_corpus(corpus_path, verify_files=False)

    assert payload["songs"][0]["path"] == str(media_root / "song.wav")
    assert validation.song_count == 1

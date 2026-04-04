from __future__ import annotations

from io import BytesIO
from pathlib import Path

from splitter.packaging import write_manifest
from splitter.util import dump_json, ensure_dir, now_iso

import audio_api
import splitter.jobs as jobs


def test_job_status_returns_rejected_candidates(job_dirs: Path) -> None:
    job_id = "job-status-fixture"
    job_root = ensure_dir(job_dirs / job_id)
    analysis_dir = ensure_dir(job_root / "analysis")
    broad_dir = ensure_dir(job_root / "broad_stems")
    specialist_dir = ensure_dir(job_root / "specialist_substems")

    stem_path = broad_dir / "vocals.wav"
    lead_path = specialist_dir / "lead_vocals.wav"
    stem_path.write_bytes(b"RIFFfixture")
    lead_path.write_bytes(b"RIFFlead")
    dump_json(
        job_root / "status.json",
        {
            "job_id": job_id,
            "profile": "quality",
            "status": "completed",
            "stage": "done",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "input_name": "fixture.wav",
            "input_path": str((job_root / "input" / "fixture.wav").resolve()),
        },
    )
    (analysis_dir / "tempo_key.json").write_text('{"tempo_bpm": 120.0}', encoding="utf-8")
    (analysis_dir / "sections.json").write_text('{"sections": []}', encoding="utf-8")
    write_manifest(
        job_root,
        {
            "job_id": job_id,
            "published_broad_stems": {
                "vocals": {
                    "path": str(stem_path.resolve()),
                    "quality_score": 1.0,
                    "publish_status": "published",
                    "publish_reason": "core_broad_stem",
                    "warnings": [],
                    "metrics": {},
                }
            },
            "published_derived_stems": {},
            "published_specialist_substems": {
                "lead_vocals": {
                    "path": str(lead_path.resolve()),
                    "quality_score": 0.91,
                    "publish_status": "published",
                    "publish_reason": "quality_score_pass",
                    "warnings": [],
                    "metrics": {},
                }
            },
            "tempo_locked_exports": {},
            "midi_exports": {},
            "analysis_exports": {
                "tempo_key": str((analysis_dir / "tempo_key.json").resolve()),
                "sections": str((analysis_dir / "sections.json").resolve()),
            },
            "bundle_exports": {},
            "remote_adapter_status": "used",
            "remote_adapter_reason": None,
            "rejected_candidates": {
                "extended_stems": {
                    "guitar": {
                        "quality_score": 0.22,
                        "publish_status": "rejected",
                        "publish_reason": "below_threshold",
                        "warnings": ["low_quality_candidate"],
                    }
                },
                "derived_stems": {},
                "specialist_substems": {},
                "midi": {},
            },
        },
    )

    client = audio_api.app.test_client()
    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["rejected_candidates"]["extended_stems"]["guitar"]["publish_reason"] == "below_threshold"
    assert payload["artifacts"]["analysis"]["sections"].endswith("/analysis/sections.json")
    assert payload["artifacts"]["specialist_substems"]["lead_vocals"].endswith("/specialist_substems/lead_vocals.wav")
    assert payload["remote_adapter_status"] == "used"


def test_separate_returns_legacy_flat_stems(job_dirs: Path, monkeypatch) -> None:
    def fake_run_job(job_id: str) -> None:
        status = jobs.get_job_status(job_id)
        assert status is not None
        job_root = ensure_dir(job_dirs / job_id)
        broad_dir = ensure_dir(job_root / "broad_stems")
        vocals_path = broad_dir / "vocals.wav"
        drums_path = broad_dir / "drums.wav"
        vocals_path.write_bytes(b"RIFFvocals")
        drums_path.write_bytes(b"RIFFdrums")
        write_manifest(
            job_root,
            {
                "job_id": job_id,
                "published_broad_stems": {
                    "vocals": {"path": str(vocals_path.resolve())},
                    "drums": {"path": str(drums_path.resolve())},
                },
                "published_derived_stems": {},
                "published_specialist_substems": {},
                "tempo_locked_exports": {},
                "midi_exports": {},
                "analysis_exports": {},
                "rejected_candidates": {
                    "extended_stems": {},
                    "derived_stems": {},
                    "specialist_substems": {},
                    "midi": {},
                },
                "bundle_exports": {},
            },
        )

    monkeypatch.setattr(audio_api, "run_job", fake_run_job)

    client = audio_api.app.test_client()
    response = client.post(
        "/separate",
        data={"file": (BytesIO(b"fixture-audio"), "fixture.wav")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload["stems"]) == {"vocals", "drums"}
    assert payload["stems"]["vocals"].startswith("/artifacts/")
    assert payload["manifest"].startswith("/jobs/")

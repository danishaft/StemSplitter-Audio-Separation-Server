from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from splitter.packaging import write_manifest
from splitter.util import dump_json, ensure_dir, now_iso

import audio_api
import splitter.jobs as jobs
import splitter.api.routers.jobs as jobs_router
import splitter.api.routers.sources as sources_router
import splitter.api.routers.uploads as uploads_router
import splitter.api.services as api_services
from splitter.object_storage import ObjectRef
from splitter.sources import AudiusImport


client = TestClient(audio_api.app)


def test_capabilities_exposes_unqualified_11_stem_evaluation_contract() -> None:
    response = client.get("/capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommended_profile"] == "quality_gpu_experimental"
    assert payload["production_profile"] is None
    assert payload["evaluation_profile"] == "quality_gpu_experimental"
    assert payload["stem_contracts"]["product_11_stems"]["target_stems"] == [
        "vocals",
        "instrumental",
        "drums",
        "bass",
        "kick",
        "snare",
        "piano",
        "acoustic_guitar",
        "electric_guitar",
        "synth",
        "strings",
    ]

    production = payload["profiles"]["quality_gpu_experimental"]
    assert production["tier"] == "evaluation"
    assert production["uses_gpu_worker"] is True
    assert production["uses_local_demucs"] is False
    assert production["fallback_policy"] == "fail_if_gpu_unavailable"
    assert "release_not_qualified" in production["warnings"]
    assert payload["quality_qualification"]["passed_initial_stems"] == [
        "electric_guitar",
        "strings",
        "synth",
    ]
    assert payload["quality_qualification"]["production_qualified_stems"] == []
    assert payload["product_contract"]["target_stems"] == [
        "vocals",
        "instrumental",
        "drums",
        "bass",
        "kick",
        "snare",
        "piano",
        "acoustic_guitar",
        "electric_guitar",
        "synth",
        "strings",
        "wind",
    ]
    assert payload["product_contract"]["model_supported_stems"] == [
        "vocals",
        "instrumental",
        "drums",
        "bass",
        "kick",
        "snare",
        "piano",
        "acoustic_guitar",
        "electric_guitar",
        "synth",
        "strings",
    ]
    assert payload["product_contract"]["specialist_candidate_stems"] == ["wind"]
    assert payload["product_contract"]["production_release_eligible"] is False

    preview = payload["profiles"]["preview"]
    assert preview["tier"] == "legacy"
    assert preview["uses_local_demucs"] is True

    audius = payload["input_sources"]["audius"]
    assert audius["enabled"] is True
    assert audius["license_policy"] == "commercial_derivatives_only"


def test_audius_search_exposes_import_decisions(monkeypatch) -> None:
    class FakeAudiusClient:
        def search(self, query, *, limit, offset):
            assert (query, limit, offset) == ("open song", 10, 0)
            return [{"id": "track123", "can_import": True, "import_reason": "license_allows_commercial_derivatives"}]

    monkeypatch.setattr(sources_router, "AudiusClient", FakeAudiusClient)

    response = client.get("/sources/audius/search?q=open+song&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "audius"
    assert payload["tracks"][0]["can_import"] is True


def test_direct_upload_returns_object_reference_without_receiving_audio(monkeypatch) -> None:
    class FakeStore:
        def create_upload(self, filename, content_type):
            assert filename == "artist-song.wav"
            assert content_type == "audio/wav"
            return {
                "method": "PUT",
                "url": "https://objects.example/upload",
                "headers": {"Content-Type": "audio/wav"},
                "object": {
                    "provider": "s3",
                    "bucket": "private-audio",
                    "key": "stemsplitter/inputs/id/artist-song.wav",
                },
            }

    monkeypatch.setattr(uploads_router, "object_store_from_config", lambda: FakeStore())

    response = client.post(
        "/uploads",
        json={"filename": "artist-song.wav", "content_type": "audio/wav"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["url"] == "https://objects.example/upload"
    assert payload["object"]["provider"] == "s3"


def test_object_reference_job_does_not_copy_audio_through_api(job_dirs: Path, monkeypatch) -> None:
    submitted = []
    reference = {
        "provider": "s3",
        "bucket": "private-audio",
        "key": "stemsplitter/inputs/id/artist-song.wav",
    }

    class FakeStore:
        def stat(self, object_reference):
            assert object_reference == reference
            return ObjectRef(
                provider="s3",
                bucket="private-audio",
                key=reference["key"],
                content_type="audio/wav",
                size_bytes=2048,
                etag="etag-123",
            )

    monkeypatch.setattr(jobs, "object_store_from_config", lambda: FakeStore())
    monkeypatch.setattr(jobs, "submit_job", submitted.append)

    response = client.post(
        "/jobs",
        json={
            "profile": "quality_gpu_experimental",
            "input": {"filename": "artist-song.wav", "object": reference},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["input_object"]["etag"] == "etag-123"
    assert not Path(payload["input_path"]).exists()
    assert submitted == [payload["job_id"]]


def test_json_job_imports_audius_track_with_source_provenance(job_dirs: Path, monkeypatch) -> None:
    submitted = []

    class FakeAudiusClient:
        def download(self, track_id):
            assert track_id == "track123"
            return AudiusImport(
                filename="open-song.wav",
                content=b"RIFF-audius",
                source={
                    "type": "catalog",
                    "provider": "audius",
                    "track_id": track_id,
                    "license": "CC BY 4.0",
                },
            )

    monkeypatch.setattr(jobs_router, "AudiusClient", FakeAudiusClient)
    monkeypatch.setattr(jobs, "submit_job", submitted.append)

    response = client.post(
        "/jobs",
        json={
            "profile": "quality_gpu_experimental",
            "source": {"provider": "audius", "track_id": "track123"},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["input_source"]["provider"] == "audius"
    assert Path(payload["input_path"]).read_bytes() == b"RIFF-audius"
    assert submitted == [payload["job_id"]]


def test_multipart_job_uses_async_dispatch(job_dirs: Path, monkeypatch) -> None:
    submitted = []
    monkeypatch.setattr(jobs, "submit_job", submitted.append)

    response = client.post(
        "/jobs",
        data={"profile": "quality"},
        files={"file": ("artist-song.wav", b"RIFF-audio", "audio/wav")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert Path(payload["input_path"]).read_bytes() == b"RIFF-audio"
    assert submitted == [payload["job_id"]]


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
            "timings": {
                "worker_total_seconds": 12.5,
                "worker_job_id": "remote-job-123",
                "updated_at": "2026-07-26T09:56:21Z",
            },
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
            "published_main_stems": {
                "vocals": {
                    "path": str(stem_path.resolve()),
                    "artifact_group": "broad_stems",
                },
                "lead_vocals": {
                    "path": str(lead_path.resolve()),
                    "artifact_group": "specialist_substems",
                },
            },
            "stem_contract": {
                "name": "quality_8_stems",
                "status": "partial",
                "published_stems": ["lead_vocals", "vocals"],
                "missing_stems": [],
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

    response = client.get(f"/jobs/{job_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["rejected_candidates"]["extended_stems"]["guitar"]["publish_reason"] == "below_threshold"
    assert payload["artifacts"]["analysis"]["sections"].endswith("/analysis/sections.json")
    assert payload["artifacts"]["main_stems"]["lead_vocals"].endswith("/specialist_substems/lead_vocals.wav")
    assert payload["artifacts"]["specialist_substems"]["lead_vocals"].endswith("/specialist_substems/lead_vocals.wav")
    assert payload["remote_adapter_status"] == "used"
    assert payload["stem_contract"]["status"] == "partial"
    assert payload["timings"]["worker_job_id"] == "remote-job-123"


def test_job_status_signs_object_artifacts_without_local_files(job_dirs: Path, monkeypatch) -> None:
    job_id = "object-artifact-job"
    job_root = ensure_dir(job_dirs / job_id)
    object_ref = {
        "provider": "s3",
        "bucket": "private-audio",
        "key": f"stemsplitter/jobs/{job_id}/broad_stems/vocals.wav",
    }
    dump_json(
        job_root / "status.json",
        {
            "job_id": job_id,
            "profile": "quality_gpu_experimental",
            "status": "completed",
            "stage": "done",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "input_name": "fixture.wav",
            "input_path": str(job_root / "input" / "fixture.wav"),
        },
    )
    write_manifest(
        job_root,
        {
            "job_id": job_id,
            "published_main_stems": {"vocals": {"storage_ref": object_ref}},
            "published_broad_stems": {"vocals": {"storage_ref": object_ref}},
            "published_derived_stems": {},
            "published_specialist_substems": {},
            "tempo_locked_exports": {},
            "midi_exports": {},
            "analysis_exports": {},
            "bundle_exports": {
                "stems": {
                    "storage_ref": {
                        "provider": "s3",
                        "bucket": "private-audio",
                        "key": f"stemsplitter/jobs/{job_id}/package/stems.zip",
                    }
                }
            },
            "rejected_candidates": {},
        },
    )

    class FakeStore:
        def signed_download_url(self, reference, filename):
            return f"https://objects.example/{reference['key']}?filename={filename}"

    monkeypatch.setattr(api_services, "object_store_from_config", lambda: FakeStore())

    payload = client.get(f"/jobs/{job_id}").json()

    assert payload["artifacts"]["main_stems"]["vocals"].startswith("https://objects.example/")
    assert payload["artifacts"]["bundles"]["stems"].endswith("?filename=stems.zip")


def test_legacy_synchronous_separation_route_is_removed() -> None:
    response = client.post("/separate")

    assert response.status_code == 404


def test_openapi_documents_job_input_contracts() -> None:
    schema = client.get("/openapi.json").json()

    request_body = schema["paths"]["/jobs"]["post"]["requestBody"]
    assert "application/json" in request_body["content"]
    assert "multipart/form-data" in request_body["content"]

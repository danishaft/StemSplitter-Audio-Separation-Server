from __future__ import annotations

import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient

import workers.audio_separator_gpu_worker as worker


@pytest.fixture(autouse=True)
def configured_worker_api_key(monkeypatch) -> None:
    monkeypatch.setattr(worker, "API_KEY", "test-worker-key")


def worker_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-worker-key"}


def test_worker_rejects_protected_requests_when_auth_is_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(worker, "API_KEY", None)

    response = TestClient(worker.api_app).get("/jobs/missing")

    assert response.status_code == 503


def test_quality_profile_uses_four_models_with_explicit_owners() -> None:
    assert set(worker.LOCAL_MODEL_REGISTRY) == {
        "melband_kim_vocals",
        "bs_roformer_sw",
        "mdx23c_drumsep_jarredou_aufr33",
        "open_specialist_product_pack",
    }
    assert worker.PROFILE_MODEL_PLANS["quality_gpu_experimental"] == [
        "melband_kim_vocals",
        "bs_roformer_sw",
        "mdx23c_drumsep_jarredou_aufr33",
        "open_specialist_product_pack",
    ]
    assert [branch["role"] for branch in worker.PARALLEL_BRANCHES] == [
        "vocals",
        "broad",
        "drums",
        "specialists",
    ]
    assert worker.LOCAL_MODEL_REGISTRY["bs_roformer_sw"]["stem_map"]["vocals"] == (
        "bs_aux_voice"
    )


def test_separate_dispatches_after_persisting_upload(tmp_path: Path, monkeypatch) -> None:
    dispatched = []

    async def no_op_commit() -> None:
        return None

    async def dispatch(job_id: str):
        dispatched.append(job_id)
        return {"execution_backend": "test_async", "execution_call_id": "call-123"}

    monkeypatch.setattr(worker, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(worker, "_commit_jobs_volume_async", no_op_commit)
    monkeypatch.setattr(worker, "_dispatch_job_async", dispatch)

    response = TestClient(worker.api_app).post(
        "/separate",
        headers=worker_headers(),
        data={"profile": "quality_gpu_experimental", "local_job_id": "friend-test-job"},
        files={"file": ("song.wav", b"RIFF-audio", "audio/wav")},
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "queued"
    assert payload["execution_backend"] == "test_async"
    assert payload["execution_call_id"] == "call-123"
    assert payload["timings"]["input_bytes"] == len(b"RIFF-audio")
    assert dispatched == ["friend-test-job"]
    assert (tmp_path / "jobs" / "friend-test-job" / "input" / "song.wav").read_bytes() == b"RIFF-audio"


def test_separate_rejects_upload_over_worker_limit(tmp_path: Path, monkeypatch) -> None:
    async def no_op_commit() -> None:
        return None

    async def reject_dispatch(job_id: str):
        raise AssertionError("oversized upload must not dispatch")

    monkeypatch.setattr(worker, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(worker, "MAX_UPLOAD_BYTES", 4)
    monkeypatch.setattr(worker, "_commit_jobs_volume_async", no_op_commit)
    monkeypatch.setattr(worker, "_dispatch_job_async", reject_dispatch)

    response = TestClient(worker.api_app).post(
        "/separate",
        headers=worker_headers(),
        files={"file": ("song.wav", b"too-large", "audio/wav")},
    )

    assert response.status_code == 413


def test_separate_reference_dispatches_without_downloading_in_api(tmp_path: Path, monkeypatch) -> None:
    dispatched = []

    async def no_op_commit() -> None:
        return None

    async def dispatch(job_id: str):
        dispatched.append(job_id)
        return {"execution_backend": "test_async", "execution_call_id": "call-object-123"}

    monkeypatch.setattr(worker, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(worker, "_commit_jobs_volume_async", no_op_commit)
    monkeypatch.setattr(worker, "_dispatch_job_async", dispatch)

    response = TestClient(worker.api_app).post(
        "/separate-reference",
        headers=worker_headers(),
        json={
            "profile": "quality_gpu_experimental",
            "local_job_id": "object-job",
            "input_name": "song.wav",
            "max_worker_seconds": 45,
            "object": {
                "provider": "s3",
                "bucket": "private-audio",
                "key": "stemsplitter/inputs/id/song.wav",
                "size_bytes": 4096,
            },
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["timings"]["input_transport"] == "object_reference"
    assert payload["max_worker_seconds"] == 45
    assert not Path(payload["input_path"]).exists()
    assert dispatched == ["object-job"]


def test_dispatch_uses_parallel_orchestrator_only_for_quality_profile(tmp_path: Path, monkeypatch) -> None:
    spawned = []

    class Call:
        object_id = "parallel-call-1"

    class Runner:
        def spawn(self, job_id: str):
            spawned.append(job_id)
            return Call()

    monkeypatch.setattr(worker, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(worker, "EXECUTION_MODE", "parallel")
    monkeypatch.setattr(worker, "process_parallel_job", Runner(), raising=False)
    worker._write_status("parallel-job", {"profile": "quality_gpu_experimental"})

    dispatch = worker._dispatch_job("parallel-job")

    assert dispatch == {
        "execution_backend": "modal_spawn",
        "execution_call_id": "parallel-call-1",
    }
    assert spawned == ["parallel-job"]


def test_parallel_finalizer_records_each_gpu_allocation(tmp_path: Path, monkeypatch) -> None:
    job_id = "parallel-finalize-job"
    monkeypatch.setattr(worker, "JOBS_DIR", tmp_path / "jobs")
    worker._write_status(
        job_id,
        {
            "profile": "quality_gpu_experimental",
            "artifacts": {},
            "artifact_sources": {},
            "missing_features": [],
            "timings": {"input_duration_seconds": 60},
        },
    )

    def finalize_contract(current_job_id, status):
        status["stem_contract"] = {"status": "complete"}
        status["rejected_candidates"] = {}
        worker._write_status(current_job_id, status)
        return status

    monkeypatch.setattr(worker, "_finalize_quality_contract", finalize_contract)
    monkeypatch.setattr(
        worker,
        "_publish_worker_objects",
        lambda current_job_id, status: {"artifact_transport": "test"},
    )
    branch_results = [
        {
            "status": "completed",
            "group": "broad_stems",
            "model": "BS-Roformer-SW.ckpt",
            "model_key": "bs_roformer_sw",
            "role": "broad",
            "gpu_type": "L4",
            "gpu_seconds": 52.0,
            "artifacts": {"vocals": f"/artifacts/{job_id}/broad_stems/vocals.wav"},
            "model_run": {"status": "completed", "duration_seconds": 50.0},
        },
        {
            "status": "completed",
            "group": "specialist_substems",
            "model": "MDX23C-DrumSep-aufr33-jarredou.ckpt",
            "model_key": "mdx23c_drumsep_jarredou_aufr33",  # gitleaks:allow
            "role": "drums",
            "gpu_type": "T4",
            "gpu_seconds": 28.0,
            "artifacts": {"kick": f"/artifacts/{job_id}/specialist_substems/kick.wav"},
            "model_run": {"status": "completed", "duration_seconds": 27.0},
        },
    ]

    worker._finalize_parallel_job(
        job_id,
        branch_results,
        job_started=time.perf_counter(),
        parallel_wait_seconds=52.5,
    )

    status = worker._load_status(job_id)
    assert status["status"] == "completed"
    assert status["artifact_transport"] == "test"
    assert status["timings"]["execution_mode"] == "heterogeneous_parallel"
    assert status["timings"]["parallel_branch_sum_seconds"] == 80.0
    assert [item["gpu_type"] for item in status["timings"]["gpu_allocations"]] == ["L4", "T4"]
    assert status["artifact_sources"]["broad_stems"]["vocals"] == "BS-Roformer-SW.ckpt"

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import splitter.api.observability as observability
from splitter.api.observability import EdgePolicyMiddleware
from splitter.api.responses import error_response
from splitter.gpu_worker_client import GPUWorkerClient, GPUWorkerError
from splitter.infrastructure.job_store import JsonJobStore
from splitter.infrastructure.rate_limit import RedisRateLimiter
from splitter.path_safety import resolve_artifact_path, resolve_job_root, safe_job_id


def test_cloudflare_origin_verification_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(observability, "APP_ENV", "production")
    monkeypatch.setattr(observability, "EDGE_MODE", "cloudflare")
    monkeypatch.setattr(observability, "EDGE_VERIFY_SECRET", "s" * 32)
    monkeypatch.setattr(observability, "RATE_LIMIT_ENABLED", False)
    app = FastAPI()
    app.add_middleware(EdgePolicyMiddleware)

    @app.get("/private")
    def private() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app)
    denied = client.get("/private")
    allowed = client.get(
        "/private",
        headers={"X-StemSplitter-Origin-Verify": "s" * 32},
    )

    assert denied.status_code == 403
    assert denied.json() == {"error": "edge_verification_failed"}
    assert allowed.status_code == 200


def test_health_check_does_not_require_edge_secret(monkeypatch) -> None:
    monkeypatch.setattr(observability, "APP_ENV", "production")
    monkeypatch.setattr(observability, "EDGE_MODE", "cloudflare")
    monkeypatch.setattr(observability, "EDGE_VERIFY_SECRET", "s" * 32)
    monkeypatch.setattr(observability, "RATE_LIMIT_ENABLED", False)
    app = FastAPI()
    app.add_middleware(EdgePolicyMiddleware)

    @app.get("/health/live")
    def live() -> dict[str, str]:
        return {"status": "ok"}

    assert TestClient(app).get("/health/live").status_code == 200


def test_rate_limiter_returns_remaining_capacity() -> None:
    limiter = object.__new__(RedisRateLimiter)
    limiter._namespace = "test"
    limiter._script = lambda *, keys, args: [3, 42]

    decision = limiter.check(scope="request", identity="127.0.0.1", limit=5)

    assert decision.allowed is True
    assert decision.remaining == 2
    assert decision.retry_after == 42


def test_gpu_worker_artifact_download_rejects_cross_origin_credentials(
    tmp_path: Path,
) -> None:
    client = GPUWorkerClient(
        base_url="https://worker.example/",
        api_key="worker-secret",
    )

    with pytest.raises(GPUWorkerError, match="artifact_origin_not_allowed"):
        client.download_artifact(
            "https://attacker.example/stolen.wav",
            tmp_path / "stolen.wav",
        )


@pytest.mark.parametrize(
    "value",
    ["../job", "job/../../outside", "/tmp/job", r"..\job", "job.json"],
)
def test_job_ids_reject_path_syntax(value: str) -> None:
    with pytest.raises(ValueError, match="invalid_job_id"):
        safe_job_id(value)


def test_job_root_stays_beneath_jobs_directory(tmp_path: Path) -> None:
    jobs_dir = tmp_path / "jobs"

    assert resolve_job_root(jobs_dir, "job_123") == jobs_dir / "job_123"
    with pytest.raises(ValueError, match="invalid_job_id"):
        resolve_job_root(jobs_dir, "../outside")


def test_artifact_path_rejects_traversal_and_prefix_collisions(tmp_path: Path) -> None:
    job_root = tmp_path / "job"

    assert resolve_artifact_path(job_root, "stems/vocals.wav") == (
        job_root / "stems" / "vocals.wav"
    )
    with pytest.raises(ValueError, match="invalid_artifact_path"):
        resolve_artifact_path(job_root, "../job-private/secret.wav")


def test_json_job_store_rejects_traversal_before_file_access(tmp_path: Path) -> None:
    store = JsonJobStore(tmp_path / "jobs")

    with pytest.raises(ValueError, match="invalid_job_id"):
        store.get("../../outside")
    assert not (tmp_path / "outside" / "status.json").exists()


def test_error_responses_only_use_predefined_public_messages() -> None:
    response = error_response(503, "object_storage_error")
    guided_response = error_response(400, "invalid_filename")

    assert response.body == b'{"error":"object_storage_error"}'
    assert b"Use an allowed audio filename." in guided_response.body

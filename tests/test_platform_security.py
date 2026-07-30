from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import splitter.api.observability as observability
from splitter.api.observability import EdgePolicyMiddleware
from splitter.gpu_worker_client import GPUWorkerClient, GPUWorkerError
from splitter.infrastructure.rate_limit import RedisRateLimiter


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

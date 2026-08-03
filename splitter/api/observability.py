from __future__ import annotations

import hmac
import logging
import re
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from splitter.bootstrap import runtime_services
from splitter.config import (
    APP_ENV,
    EDGE_MODE,
    EDGE_VERIFY_HEADER,
    EDGE_VERIFY_SECRET,
    MAX_CONTENT_LENGTH,
    METRICS_BEARER_TOKEN,
    RATE_LIMIT_ENABLED,
    RATE_LIMIT_MUTATIONS_PER_MINUTE,
    RATE_LIMIT_REQUESTS_PER_MINUTE,
)
from splitter.infrastructure.rate_limit import RateLimitUnavailable
from splitter.observability import request_id_context

logger = logging.getLogger("stemsplitter.api")
router = APIRouter(tags=["system"])
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
EDGE_BYPASS_PATHS = {"/health/live", "/health/ready", "/health/version"}
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    REQUEST_COUNT = Counter(
        "stemsplitter_http_requests_total",
        "HTTP requests handled by the API.",
        ("method", "route", "status"),
    )
    REQUEST_DURATION = Histogram(
        "stemsplitter_http_request_seconds",
        "HTTP request duration in seconds.",
        ("method", "route"),
    )
except ImportError:  # pragma: no cover - production dependency is required
    CONTENT_TYPE_LATEST = "text/plain"
    REQUEST_COUNT = REQUEST_DURATION = None
    generate_latest = None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        requested_id = headers.get("x-request-id", "")
        request_id = (
            requested_id
            if REQUEST_ID_PATTERN.fullmatch(requested_id)
            else uuid.uuid4().hex
        )
        context_token = request_id_context.set(request_id)
        status_code = 500

        async def send_with_context(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                response_headers.append((b"x-content-type-options", b"nosniff"))
                response_headers.append((b"x-frame-options", b"DENY"))
                response_headers.append((b"referrer-policy", b"no-referrer"))
                response_headers.append(
                    (
                        b"permissions-policy",
                        b"camera=(), microphone=(), geolocation=(), payment=()",
                    )
                )
                if APP_ENV == "production":
                    response_headers.append(
                        (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                    )
                    response_headers.append(
                        (
                            b"content-security-policy",
                            b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
                        )
                    )
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_context)
        finally:
            elapsed = time.perf_counter() - started
            route = scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            if REQUEST_COUNT is not None:
                REQUEST_COUNT.labels(scope["method"], route_path, str(status_code)).inc()
            if REQUEST_DURATION is not None:
                REQUEST_DURATION.labels(scope["method"], route_path).observe(elapsed)
            logger.info(
                "request_complete method=%s route=%s status=%s duration_ms=%.3f",
                scope["method"],
                route_path,
                status_code,
                elapsed * 1000,
            )
            request_id_context.reset(context_token)


class ContentLengthLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            try:
                too_large = int(headers.get("content-length", "0")) > MAX_CONTENT_LENGTH
            except ValueError:
                too_large = False
            if too_large:
                response = Response(
                    '{"error":"request_too_large"}',
                    status_code=413,
                    media_type="application/json",
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class EdgePolicyMiddleware:
    """Enforce origin trust and shared Redis limits behind Cloudflare."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "/")
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if (
            APP_ENV == "production"
            and EDGE_MODE == "cloudflare"
            and path not in EDGE_BYPASS_PATHS
        ):
            supplied = headers.get(EDGE_VERIFY_HEADER.lower(), "")
            if not EDGE_VERIFY_SECRET or not hmac.compare_digest(
                supplied,
                EDGE_VERIFY_SECRET,
            ):
                await _json_error(403, "edge_verification_failed", scope, receive, send)
                return

        if RATE_LIMIT_ENABLED and path not in EDGE_BYPASS_PATHS:
            method = str(scope.get("method") or "GET").upper()
            mutation = method in MUTATING_METHODS
            limit = (
                RATE_LIMIT_MUTATIONS_PER_MINUTE
                if mutation
                else RATE_LIMIT_REQUESTS_PER_MINUTE
            )
            peer = scope.get("client")
            identity = (
                headers.get("cf-connecting-ip")
                if EDGE_MODE == "cloudflare"
                else None
            ) or (str(peer[0]) if peer else "unknown")
            limiter = runtime_services().rate_limiter()
            if limiter is not None:
                try:
                    decision = limiter.check(
                        scope="mutation" if mutation else "request",
                        identity=identity,
                        limit=limit,
                    )
                except RateLimitUnavailable:
                    if APP_ENV == "production":
                        await _json_error(
                            503,
                            "rate_limit_unavailable",
                            scope,
                            receive,
                            send,
                        )
                        return
                else:
                    if not decision.allowed:
                        response = Response(
                            '{"error":"rate_limit_exceeded"}',
                            status_code=429,
                            media_type="application/json",
                            headers={
                                "Retry-After": str(decision.retry_after),
                                "X-RateLimit-Limit": str(decision.limit),
                                "X-RateLimit-Remaining": "0",
                            },
                        )
                        await response(scope, receive, send)
                        return
        await self.app(scope, receive, send)


async def _json_error(
    status_code: int,
    code: str,
    scope: Scope,
    receive: Receive,
    send: Send,
) -> None:
    response = Response(
        f'{{"error":"{code}"}}',
        status_code=status_code,
        media_type="application/json",
    )
    await response(scope, receive, send)


@router.get("/metrics", operation_id="getMetrics")
def metrics(request: Request) -> Response:
    if METRICS_BEARER_TOKEN:
        supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(supplied, METRICS_BEARER_TOKEN):
            return Response(
                '{"error":"metrics_authentication_required"}',
                status_code=401,
                media_type="application/json",
            )
    if generate_latest is None:
        return Response(
            "prometheus_client_not_installed\n",
            status_code=503,
            media_type="text/plain",
        )
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

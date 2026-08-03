from __future__ import annotations

import time
from dataclasses import dataclass


class RateLimitUnavailable(RuntimeError):
    """Raised when a production rate-limit decision cannot be made."""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


class RedisRateLimiter:
    """Atomic fixed-window limiter shared by every API replica."""

    _SCRIPT = """
    local current = redis.call('INCR', KEYS[1])
    if current == 1 then
      redis.call('EXPIRE', KEYS[1], ARGV[1])
    end
    local ttl = redis.call('TTL', KEYS[1])
    return {current, ttl}
    """

    def __init__(self, redis_url: str, namespace: str) -> None:
        try:
            from redis import Redis
        except ImportError as exc:  # pragma: no cover - runtime dependency
            raise RateLimitUnavailable("redis_dependency_missing") from exc
        self._client = Redis.from_url(
            redis_url,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
        )
        self._namespace = namespace.strip(":")
        self._script = self._client.register_script(self._SCRIPT)

    def check(
        self,
        *,
        scope: str,
        identity: str,
        limit: int,
        window_seconds: int = 60,
    ) -> RateLimitDecision:
        window = max(1, window_seconds)
        bucket = int(time.time()) // window
        key = f"{self._namespace}:{scope}:{identity}:{bucket}"
        try:
            current, ttl = self._script(keys=[key], args=[window + 1])
        except Exception as exc:
            raise RateLimitUnavailable("rate_limit_backend_unavailable") from exc
        count = int(current)
        retry_after = max(1, int(ttl))
        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after=retry_after,
        )

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception as exc:
            raise RateLimitUnavailable("rate_limit_backend_unavailable") from exc

    def close(self) -> None:
        self._client.close()

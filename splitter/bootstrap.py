from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import RLock

from .config import (
    DATABASE_POOL_MAX_SIZE,
    DATABASE_POOL_MIN_SIZE,
    DATABASE_POOL_TIMEOUT,
    DATABASE_URL,
    JOB_DISPATCH_BACKEND,
    JOB_EXECUTION_TIMEOUT,
    JOB_FAILURE_TTL,
    JOB_MAX_ATTEMPTS,
    JOB_QUEUE_NAME,
    JOB_RESULT_TTL,
    JOB_RETRY_INTERVALS,
    JOB_STORE_BACKEND,
    JOBS_DIR,
    RATE_LIMIT_NAMESPACE,
    REDIS_URL,
)
from .infrastructure.dispatch import (
    JobDispatcher,
    RQJobDispatcher,
    ThreadJobDispatcher,
)
from .infrastructure.job_store import JobStore, JsonJobStore, PostgresJobStore
from .infrastructure.object_storage import shutdown_object_store
from .infrastructure.rate_limit import RedisRateLimiter


class RuntimeServices:
    """Own process-local infrastructure adapters and their lifecycle."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._job_store: JobStore | None = None
        self._dispatcher: JobDispatcher | None = None
        self._rate_limiter: RedisRateLimiter | None = None

    def job_store(self, *, jobs_dir: Path | None = None) -> JobStore:
        with self._lock:
            resolved_jobs_dir = jobs_dir or JOBS_DIR
            if (
                isinstance(self._job_store, JsonJobStore)
                and self._job_store.jobs_dir != resolved_jobs_dir
            ):
                self._job_store.close()
                self._job_store = None
            if self._job_store is not None:
                return self._job_store
            if JOB_STORE_BACKEND == "json":
                self._job_store = JsonJobStore(resolved_jobs_dir)
            elif JOB_STORE_BACKEND == "postgres":
                if not DATABASE_URL:
                    raise RuntimeError("database_url_missing")
                self._job_store = PostgresJobStore(
                    DATABASE_URL,
                    min_size=DATABASE_POOL_MIN_SIZE,
                    max_size=DATABASE_POOL_MAX_SIZE,
                    timeout=DATABASE_POOL_TIMEOUT,
                )
            else:
                raise RuntimeError(
                    f"unsupported_job_store_backend:{JOB_STORE_BACKEND}"
                )
            return self._job_store

    def dispatcher(self, runner: Callable[[str], None]) -> JobDispatcher:
        with self._lock:
            if self._dispatcher is not None:
                return self._dispatcher
            if JOB_DISPATCH_BACKEND == "thread":
                self._dispatcher = ThreadJobDispatcher(runner)
            elif JOB_DISPATCH_BACKEND == "rq":
                if not REDIS_URL:
                    raise RuntimeError("redis_url_missing")
                self._dispatcher = RQJobDispatcher(
                    redis_url=REDIS_URL,
                    queue_name=JOB_QUEUE_NAME,
                    result_ttl=JOB_RESULT_TTL,
                    failure_ttl=JOB_FAILURE_TTL,
                    execution_timeout=JOB_EXECUTION_TIMEOUT,
                    max_attempts=JOB_MAX_ATTEMPTS,
                    retry_intervals=JOB_RETRY_INTERVALS,
                )
            else:
                raise RuntimeError(
                    f"unsupported_job_dispatch_backend:{JOB_DISPATCH_BACKEND}"
                )
            return self._dispatcher

    def rate_limiter(self) -> RedisRateLimiter | None:
        with self._lock:
            if self._rate_limiter is not None:
                return self._rate_limiter
            if not REDIS_URL:
                return None
            self._rate_limiter = RedisRateLimiter(REDIS_URL, RATE_LIMIT_NAMESPACE)
            return self._rate_limiter

    def close(self) -> None:
        with self._lock:
            if self._dispatcher is not None:
                self._dispatcher.close()
                self._dispatcher = None
            if self._job_store is not None:
                self._job_store.close()
            self._job_store = None
            if self._rate_limiter is not None:
                self._rate_limiter.close()
                self._rate_limiter = None
            shutdown_object_store()


_SERVICES = RuntimeServices()


def runtime_services() -> RuntimeServices:
    return _SERVICES


def shutdown_runtime_services() -> None:
    _SERVICES.close()

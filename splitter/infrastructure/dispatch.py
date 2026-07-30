from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import RLock
from typing import Protocol

logger = logging.getLogger("stemsplitter.dispatch")


class DispatchError(RuntimeError):
    """Raised when a job cannot be queued or cancelled."""


class JobDispatcher(Protocol):
    def ping(self) -> bool: ...

    def enqueue(self, job_id: str) -> str: ...

    def recover(self, job_id: str, attempt: int) -> str: ...

    def cancel(self, job_id: str) -> bool: ...

    def close(self) -> None: ...


class ThreadJobDispatcher:
    """Single-process development dispatcher; never use this in production."""

    def __init__(self, runner: Callable[[str], None], max_workers: int = 1) -> None:
        self.runner = runner
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures: dict[str, Future[None]] = {}
        self.lock = RLock()

    def enqueue(self, job_id: str) -> str:
        with self.lock:
            existing = self.futures.get(job_id)
            if existing is None or existing.done():
                future = self.executor.submit(self.runner, job_id)
                self.futures[job_id] = future
                future.add_done_callback(
                    lambda completed, queued_job_id=job_id: self._on_complete(
                        queued_job_id,
                        completed,
                    )
                )
        return f"thread:{job_id}"

    def _on_complete(self, job_id: str, future: Future[None]) -> None:
        try:
            future.result()
        except Exception:
            logger.exception("development_job_failed job_id=%s", job_id)
        finally:
            with self.lock:
                if self.futures.get(job_id) is future:
                    self.futures.pop(job_id, None)

    def recover(self, job_id: str, attempt: int) -> str:
        return self.enqueue(job_id)

    def ping(self) -> bool:
        return True

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            future = self.futures.get(job_id)
            return bool(future and future.cancel())

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)


@dataclass(frozen=True)
class RQJobDispatcher:
    redis_url: str
    queue_name: str
    result_ttl: int
    failure_ttl: int
    execution_timeout: int
    max_attempts: int = 3
    retry_intervals: tuple[int, ...] = (10, 30)

    def _queue(self):
        try:
            from redis import Redis
            from rq import Queue
        except ImportError as exc:
            raise DispatchError("rq_dependencies_not_installed") from exc
        return Queue(self.queue_name, connection=Redis.from_url(self.redis_url))

    def _enqueue(self, job_id: str, rq_job_id: str) -> str:
        queue = self._queue()
        existing = queue.fetch_job(rq_job_id)
        if existing is not None and existing.get_status(refresh=True) in {
            "queued",
            "started",
            "deferred",
            "scheduled",
        }:
            return rq_job_id
        if existing is not None:
            existing.delete()
        enqueue_options = {
            "job_id": rq_job_id,
            "result_ttl": self.result_ttl,
            "failure_ttl": self.failure_ttl,
            "job_timeout": self.execution_timeout,
        }
        if self.max_attempts > 1:
            from rq import Retry

            intervals = self.retry_intervals[: self.max_attempts - 1]
            enqueue_options["retry"] = Retry(
                max=self.max_attempts - 1,
                interval=intervals or 0,
            )
        queue.enqueue(
            "splitter.jobs.run_job",
            job_id,
            **enqueue_options,
        )
        return rq_job_id

    def enqueue(self, job_id: str) -> str:
        return self._enqueue(job_id, f"stemsplitter-{job_id}")

    def recover(self, job_id: str, attempt: int) -> str:
        return self._enqueue(
            job_id,
            f"stemsplitter-{job_id}-recovery-{max(1, attempt)}",
        )

    def ping(self) -> bool:
        return bool(self._queue().connection.ping())

    def cancel(self, job_id: str) -> bool:
        queue = self._queue()
        job = queue.fetch_job(f"stemsplitter-{job_id}")
        if job is None:
            return False
        try:
            from rq.command import send_stop_job_command

            if job.get_status(refresh=True) == "started":
                send_stop_job_command(queue.connection, job.id)
            else:
                job.cancel()
            return True
        except Exception as exc:
            raise DispatchError("rq_cancel_failed") from exc

    def close(self) -> None:
        return None

from __future__ import annotations

import shutil
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from ..path_safety import resolve_job_root
from ..util import dump_json, load_json, now_iso

TERMINAL_JOB_STATES = {"completed", "error", "failed", "cancelled"}
ACTIVE_JOB_STATES = {"queued", "running", "finalizing", "cancelling"}
JOB_TRANSITIONS = {
    "queued": {"running", "error", "failed", "cancelled"},
    "running": {"queued", "finalizing", "cancelling", "completed", "error", "failed", "cancelled"},
    "finalizing": {"queued", "cancelling", "completed", "error", "failed", "cancelled"},
    "cancelling": {"cancelled", "error", "failed"},
    "error": {"queued", "cancelled"},
    "failed": {"queued", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}
_LOCAL_LOCK = RLock()


class JobStoreError(RuntimeError):
    """Raised when durable job state cannot be read or changed."""


class JobStore(Protocol):
    def ping(self) -> bool: ...

    def close(self) -> None: ...

    def create(
        self,
        payload: Mapping[str, Any],
        *,
        owner_id: str,
        idempotency_key: str | None,
        max_active: int,
        max_active_per_owner: int,
    ) -> tuple[dict[str, Any], bool]: ...

    def get(self, job_id: str) -> dict[str, Any] | None: ...

    def update(self, job_id: str, updates: Mapping[str, Any]) -> dict[str, Any]: ...

    def acquire_lease(self, job_id: str, owner: str, lease_seconds: int) -> bool: ...

    def renew_lease(self, job_id: str, owner: str, lease_seconds: int) -> bool: ...

    def release_lease(self, job_id: str, owner: str) -> None: ...

    def request_cancel(self, job_id: str) -> dict[str, Any] | None: ...

    def list_reconcilable(self, stale_seconds: int, limit: int = 100) -> list[dict[str, Any]]: ...

    def list_events(self, job_id: str, after_id: int = 0, limit: int = 100) -> list[dict[str, Any]]: ...

    def list_expired(self, retention_seconds: int, limit: int = 100) -> list[dict[str, Any]]: ...

    def delete(self, job_id: str) -> bool: ...

    def claim_dispatches(
        self,
        owner: str,
        *,
        limit: int = 100,
        lease_seconds: int = 60,
    ) -> list[dict[str, Any]]: ...

    def mark_dispatched(self, job_id: str, dispatch_id: str) -> None: ...

    def mark_dispatch_failed(
        self,
        job_id: str,
        error: str,
        *,
        retry_seconds: int = 30,
    ) -> None: ...


class JsonJobStore:
    """Single-machine development store retained outside production mode."""

    def __init__(self, jobs_dir: Path) -> None:
        self.jobs_dir = jobs_dir
        self.idempotency_path = jobs_dir / ".idempotency.json"

    def _status_path(self, job_id: str) -> Path:
        return resolve_job_root(self.jobs_dir, job_id) / "status.json"

    def _events_path(self, job_id: str) -> Path:
        return resolve_job_root(self.jobs_dir, job_id) / "events.json"

    def _append_event(self, job_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        path = self._events_path(job_id)
        events = load_json(path) if path.exists() else []
        event_id = int(events[-1]["id"]) + 1 if events else 1
        events.append(
            {
                "id": event_id,
                "event_type": event_type,
                "payload": dict(payload),
                "created_at": now_iso(),
            }
        )
        dump_json(path, events)

    def ping(self) -> bool:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        return self.jobs_dir.is_dir()

    def close(self) -> None:
        return None

    def create(
        self,
        payload: Mapping[str, Any],
        *,
        owner_id: str,
        idempotency_key: str | None,
        max_active: int,
        max_active_per_owner: int,
    ) -> tuple[dict[str, Any], bool]:
        job_id = str(payload["job_id"])
        with _LOCAL_LOCK:
            self.jobs_dir.mkdir(parents=True, exist_ok=True)
            if idempotency_key:
                index = load_json(self.idempotency_path) if self.idempotency_path.exists() else {}
                existing_id = index.get(f"{owner_id}:{idempotency_key}")
                if existing_id:
                    existing = self.get(str(existing_id))
                    if existing is not None:
                        return existing, False
            active_jobs = [
                job
                for path in self.jobs_dir.glob("*/status.json")
                if (job := load_json(path)).get("status") in ACTIVE_JOB_STATES
            ]
            if max_active > 0 and len(active_jobs) >= max_active:
                raise JobStoreError("job_capacity_exceeded")
            owner_active = sum(job.get("owner_id") == owner_id for job in active_jobs)
            if max_active_per_owner > 0 and owner_active >= max_active_per_owner:
                raise JobStoreError("owner_job_capacity_exceeded")
            status = {
                **dict(payload),
                "owner_id": owner_id,
                "idempotency_key": idempotency_key,
                "cancel_requested": False,
                "attempt": 0,
            }
            self._status_path(job_id).parent.mkdir(parents=True, exist_ok=True)
            dump_json(self._status_path(job_id), status)
            self._append_event(job_id, "created", {"status": status["status"]})
            if idempotency_key:
                index[f"{owner_id}:{idempotency_key}"] = job_id
                dump_json(self.idempotency_path, index)
            return status, True

    def get(self, job_id: str) -> dict[str, Any] | None:
        path = self._status_path(job_id)
        return load_json(path) if path.exists() else None

    def update(self, job_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        with _LOCAL_LOCK:
            current = self.get(job_id)
            if current is None:
                raise JobStoreError(f"job_not_found:{job_id}")
            _validate_transition(str(current.get("status") or "queued"), updates.get("status"))
            current.update(dict(updates))
            current["updated_at"] = now_iso()
            dump_json(self._status_path(job_id), current)
            event_payload = {
                key: current.get(key)
                for key in (
                    "status",
                    "stage",
                    "error",
                    "gpu_worker_status",
                    "gpu_worker_job_id",
                    "cancellation_status",
                )
                if key in updates
            }
            self._append_event(
                job_id,
                str(current.get("stage") or current.get("status") or "updated"),
                event_payload,
            )
            return current

    def acquire_lease(self, job_id: str, owner: str, lease_seconds: int) -> bool:
        with _LOCAL_LOCK:
            current = self.get(job_id)
            if current is None or current.get("status") in TERMINAL_JOB_STATES:
                return False
            expires_at = _parse_timestamp(current.get("lease_expires_at"))
            now = datetime.now(UTC)
            if current.get("lease_owner") not in {None, owner} and expires_at and expires_at > now:
                return False
            self.update(
                job_id,
                {
                    "lease_owner": owner,
                    "lease_expires_at": _future_iso(lease_seconds),
                    "attempt": int(current.get("attempt") or 0) + 1,
                },
            )
            return True

    def renew_lease(self, job_id: str, owner: str, lease_seconds: int) -> bool:
        with _LOCAL_LOCK:
            current = self.get(job_id)
            if current is None or current.get("lease_owner") != owner:
                return False
            self.update(job_id, {"lease_expires_at": _future_iso(lease_seconds)})
            return True

    def release_lease(self, job_id: str, owner: str) -> None:
        with _LOCAL_LOCK:
            current = self.get(job_id)
            if current is not None and current.get("lease_owner") == owner:
                self.update(job_id, {"lease_owner": None, "lease_expires_at": None})

    def request_cancel(self, job_id: str) -> dict[str, Any] | None:
        with _LOCAL_LOCK:
            current = self.get(job_id)
            if current is None:
                return None
            if current.get("status") in TERMINAL_JOB_STATES:
                return current
            updates: dict[str, Any] = {"cancel_requested": True}
            if current.get("status") == "queued":
                updates.update(status="cancelled", stage="cancelled")
            elif current.get("status") in {"running", "finalizing"}:
                updates.update(status="cancelling", stage="cancelling")
            return self.update(job_id, updates)

    def list_reconcilable(self, stale_seconds: int, limit: int = 100) -> list[dict[str, Any]]:
        cutoff = datetime.now(UTC).timestamp() - stale_seconds
        results: list[dict[str, Any]] = []
        if not self.jobs_dir.exists():
            return results
        for path in sorted(self.jobs_dir.glob("*/status.json")):
            payload = load_json(path)
            updated = _parse_timestamp(payload.get("updated_at"))
            if payload.get("status") in ACTIVE_JOB_STATES and (
                updated is None or updated.timestamp() <= cutoff
            ):
                results.append(payload)
            if len(results) >= limit:
                break
        return results

    def list_events(self, job_id: str, after_id: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        path = self._events_path(job_id)
        if not path.exists():
            return []
        events = load_json(path)
        return [event for event in events if int(event.get("id") or 0) > after_id][:limit]

    def list_expired(self, retention_seconds: int, limit: int = 100) -> list[dict[str, Any]]:
        cutoff = datetime.now(UTC).timestamp() - retention_seconds
        results: list[dict[str, Any]] = []
        if not self.jobs_dir.exists():
            return results
        for path in sorted(self.jobs_dir.glob("*/status.json")):
            payload = load_json(path)
            updated = _parse_timestamp(payload.get("updated_at") or payload.get("created_at"))
            if payload.get("status") in TERMINAL_JOB_STATES and updated and updated.timestamp() <= cutoff:
                results.append(payload)
            if len(results) >= limit:
                break
        return results

    def delete(self, job_id: str) -> bool:
        with _LOCAL_LOCK:
            if self.get(job_id) is None:
                return False
            shutil.rmtree(resolve_job_root(self.jobs_dir, job_id), ignore_errors=True)
            if self.idempotency_path.exists():
                index = load_json(self.idempotency_path)
                retained = {key: value for key, value in index.items() if value != job_id}
                dump_json(self.idempotency_path, retained)
            return True

    def claim_dispatches(
        self,
        owner: str,
        *,
        limit: int = 100,
        lease_seconds: int = 60,
    ) -> list[dict[str, Any]]:
        del owner, limit, lease_seconds
        return []

    def mark_dispatched(self, job_id: str, dispatch_id: str) -> None:
        del job_id, dispatch_id

    def mark_dispatch_failed(
        self,
        job_id: str,
        error: str,
        *,
        retry_seconds: int = 30,
    ) -> None:
        del job_id, error, retry_seconds


class PostgresJobStore:
    """PostgreSQL authority for multi-instance job state and execution leases."""

    def __init__(
        self,
        database_url: str,
        *,
        min_size: int = 1,
        max_size: int = 10,
        timeout: float = 10.0,
    ) -> None:
        if not database_url:
            raise JobStoreError("database_url_missing")
        self.database_url = database_url
        try:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise JobStoreError("psycopg_pool_not_installed") from exc
        try:
            self.pool = ConnectionPool(
                conninfo=database_url,
                min_size=max(1, min_size),
                max_size=max(max_size, min_size, 1),
                timeout=max(1.0, timeout),
                kwargs={"row_factory": dict_row},
                open=True,
            )
        except Exception as exc:
            raise JobStoreError("postgres_job_store_unavailable") from exc

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        try:
            with self.pool.connection() as connection:
                yield connection
        except JobStoreError:
            raise
        except Exception as exc:
            raise JobStoreError("postgres_job_store_unavailable") from exc

    def close(self) -> None:
        self.pool.close()

    def create(
        self,
        payload: Mapping[str, Any],
        *,
        owner_id: str,
        idempotency_key: str | None,
        max_active: int,
        max_active_per_owner: int,
    ) -> tuple[dict[str, Any], bool]:
        from psycopg.types.json import Jsonb

        status = {
            **dict(payload),
            "owner_id": owner_id,
            "idempotency_key": idempotency_key,
            "cancel_requested": False,
            "attempt": 0,
        }
        with self._connection() as connection:
            # Serialize admission across API instances without adding a second
            # queue authority. PostgreSQL remains the source of truth.
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext('stemsplitter-job-admission'))"
            )
            if idempotency_key:
                existing = connection.execute(
                    "SELECT payload FROM jobs WHERE owner_id = %s AND idempotency_key = %s",
                    (owner_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    return dict(existing["payload"]), False
            active_count = connection.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE status = ANY(%s)",
                (list(ACTIVE_JOB_STATES),),
            ).fetchone()["count"]
            if max_active > 0 and active_count >= max_active:
                raise JobStoreError("job_capacity_exceeded")
            owner_active = connection.execute(
                "SELECT COUNT(*) AS count FROM jobs WHERE owner_id = %s AND status = ANY(%s)",
                (owner_id, list(ACTIVE_JOB_STATES)),
            ).fetchone()["count"]
            if max_active_per_owner > 0 and owner_active >= max_active_per_owner:
                raise JobStoreError("owner_job_capacity_exceeded")
            row = connection.execute(
                """
                INSERT INTO jobs (
                    id, owner_id, idempotency_key, profile, status, stage, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (owner_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL
                DO NOTHING
                RETURNING payload
                """,
                (
                    status["job_id"],
                    owner_id,
                    idempotency_key,
                    status["profile"],
                    status["status"],
                    status.get("stage"),
                    Jsonb(status),
                ),
            ).fetchone()
            if row is not None:
                connection.execute(
                    "INSERT INTO job_events (job_id, event_type, payload) VALUES (%s, 'created', %s)",
                    (status["job_id"], Jsonb({"status": status["status"]})),
                )
                connection.execute(
                    """
                    INSERT INTO job_dispatch_outbox (job_id)
                    VALUES (%s)
                    ON CONFLICT (job_id) DO NOTHING
                    """,
                    (status["job_id"],),
                )
                return dict(row["payload"]), True
            existing = connection.execute(
                "SELECT payload FROM jobs WHERE owner_id = %s AND idempotency_key = %s",
                (owner_id, idempotency_key),
            ).fetchone()
            if existing is None:
                raise JobStoreError("idempotency_conflict_without_job")
            return dict(existing["payload"]), False

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT payload FROM jobs WHERE id = %s", (job_id,)).fetchone()
            return dict(row["payload"]) if row is not None else None

    def ping(self) -> bool:
        with self._connection() as connection:
            return connection.execute("SELECT 1 AS ready").fetchone()["ready"] == 1

    def update(self, job_id: str, updates: Mapping[str, Any]) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        stamped = {**dict(updates), "updated_at": now_iso()}
        with self._connection() as connection:
            current = connection.execute(
                "SELECT status FROM jobs WHERE id = %s FOR UPDATE",
                (job_id,),
            ).fetchone()
            if current is None:
                raise JobStoreError(f"job_not_found:{job_id}")
            _validate_transition(str(current["status"]), stamped.get("status"))
            row = connection.execute(
                """
                UPDATE jobs
                SET payload = payload || %s,
                    status = COALESCE(%s, status),
                    stage = COALESCE(%s, stage),
                    worker_job_id = COALESCE(%s, worker_job_id),
                    cancel_requested = COALESCE(%s, cancel_requested),
                    updated_at = NOW()
                WHERE id = %s
                  AND status NOT IN ('completed', 'cancelled')
                RETURNING payload
                """,
                (
                    Jsonb(stamped),
                    stamped.get("status"),
                    stamped.get("stage"),
                    stamped.get("gpu_worker_job_id"),
                    stamped.get("cancel_requested"),
                    job_id,
                ),
            ).fetchone()
            if row is None:
                raise JobStoreError(f"job_not_found:{job_id}")
            event_payload = {
                key: stamped[key]
                for key in (
                    "status",
                    "stage",
                    "error",
                    "gpu_worker_status",
                    "gpu_worker_job_id",
                    "cancellation_status",
                )
                if key in stamped
            }
            connection.execute(
                "INSERT INTO job_events (job_id, event_type, payload) VALUES (%s, %s, %s)",
                (
                    job_id,
                    str(stamped.get("stage") or stamped.get("status") or "updated"),
                    Jsonb(event_payload),
                ),
            )
            return dict(row["payload"])

    def acquire_lease(self, job_id: str, owner: str, lease_seconds: int) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                UPDATE jobs
                SET lease_owner = %s,
                    lease_expires_at = NOW() + make_interval(secs => %s),
                    attempt = attempt + 1,
                    payload = payload || jsonb_build_object(
                        'lease_owner', %s::text,
                        'lease_expires_at', NOW() + make_interval(secs => %s),
                        'attempt', attempt + 1
                    ),
                    updated_at = NOW()
                WHERE id = %s
                  AND status NOT IN ('completed', 'error', 'failed', 'cancelled')
                  AND (lease_expires_at IS NULL OR lease_expires_at < NOW() OR lease_owner = %s)
                RETURNING id
                """,
                (owner, lease_seconds, owner, lease_seconds, job_id, owner),
            ).fetchone()
            return row is not None

    def renew_lease(self, job_id: str, owner: str, lease_seconds: int) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                """
                UPDATE jobs
                SET lease_expires_at = NOW() + make_interval(secs => %s),
                    payload = payload || jsonb_build_object(
                        'lease_expires_at', NOW() + make_interval(secs => %s)
                    ),
                    updated_at = NOW()
                WHERE id = %s AND lease_owner = %s
                RETURNING id
                """,
                (lease_seconds, lease_seconds, job_id, owner),
            ).fetchone()
            return row is not None

    def release_lease(self, job_id: str, owner: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET lease_owner = NULL,
                    lease_expires_at = NULL,
                    payload = payload || '{"lease_owner": null, "lease_expires_at": null}'::jsonb,
                    updated_at = NOW()
                WHERE id = %s AND lease_owner = %s
                """,
                (job_id, owner),
            )

    def request_cancel(self, job_id: str) -> dict[str, Any] | None:
        from psycopg.types.json import Jsonb

        with self._connection() as connection:
            row = connection.execute(
                """
                UPDATE jobs
                SET cancel_requested = TRUE,
                    status = CASE
                        WHEN status = 'queued' THEN 'cancelled'
                        WHEN status IN ('running', 'finalizing') THEN 'cancelling'
                        ELSE status
                    END,
                    stage = CASE
                        WHEN status = 'queued' THEN 'cancelled'
                        WHEN status IN ('running', 'finalizing') THEN 'cancelling'
                        ELSE stage
                    END,
                    payload = payload || jsonb_build_object(
                        'cancel_requested', TRUE,
                        'status', CASE
                            WHEN status = 'queued' THEN 'cancelled'
                            WHEN status IN ('running', 'finalizing') THEN 'cancelling'
                            ELSE status
                        END,
                        'stage', CASE
                            WHEN status = 'queued' THEN 'cancelled'
                            WHEN status IN ('running', 'finalizing') THEN 'cancelling'
                            ELSE stage
                        END,
                        'updated_at', NOW()
                    ),
                    updated_at = NOW()
                WHERE id = %s
                RETURNING payload
                """,
                (job_id,),
            ).fetchone()
            if row is None:
                existing = connection.execute(
                    "SELECT payload FROM jobs WHERE id = %s",
                    (job_id,),
                ).fetchone()
                return dict(existing["payload"]) if existing is not None else None
            payload = dict(row["payload"])
            connection.execute(
                "INSERT INTO job_events (job_id, event_type, payload) VALUES (%s, %s, %s)",
                (
                    job_id,
                    str(payload.get("stage") or "cancelling"),
                    Jsonb(
                        {
                            "status": payload.get("status"),
                            "stage": payload.get("stage"),
                            "cancel_requested": True,
                        }
                    ),
                ),
            )
            return payload

    def list_reconcilable(self, stale_seconds: int, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM jobs
                WHERE status IN ('queued', 'running', 'finalizing', 'cancelling')
                  AND updated_at < NOW() - make_interval(secs => %s)
                  AND (
                      status = 'queued'
                      OR lease_expires_at IS NULL
                      OR lease_expires_at < NOW()
                  )
                ORDER BY updated_at
                LIMIT %s
                """,
                (stale_seconds, limit),
            ).fetchall()
            return [dict(row["payload"]) for row in rows]

    def list_events(self, job_id: str, after_id: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, payload, created_at
                FROM job_events
                WHERE job_id = %s AND id > %s
                ORDER BY id
                LIMIT %s
                """,
                (job_id, after_id, limit),
            ).fetchall()
            return [
                {
                    "id": int(row["id"]),
                    "event_type": row["event_type"],
                    "payload": dict(row["payload"]),
                    "created_at": row["created_at"].isoformat(),
                }
                for row in rows
            ]

    def list_expired(self, retention_seconds: int, limit: int = 100) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload
                FROM jobs
                WHERE status = ANY(%s)
                  AND updated_at < NOW() - make_interval(secs => %s)
                ORDER BY updated_at
                LIMIT %s
                """,
                (list(TERMINAL_JOB_STATES), retention_seconds, limit),
            ).fetchall()
            return [dict(row["payload"]) for row in rows]

    def delete(self, job_id: str) -> bool:
        with self._connection() as connection:
            row = connection.execute(
                "DELETE FROM jobs WHERE id = %s RETURNING id",
                (job_id,),
            ).fetchone()
            return row is not None

    def claim_dispatches(
        self,
        owner: str,
        *,
        limit: int = 100,
        lease_seconds: int = 60,
    ) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                WITH candidates AS (
                    SELECT id
                    FROM job_dispatch_outbox
                    WHERE dispatched_at IS NULL
                      AND available_at <= NOW()
                      AND (
                        locked_at IS NULL
                        OR locked_at < NOW() - make_interval(secs => %s)
                      )
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE job_dispatch_outbox AS outbox
                SET locked_at = NOW(),
                    locked_by = %s,
                    attempts = outbox.attempts + 1
                FROM candidates
                WHERE outbox.id = candidates.id
                RETURNING outbox.job_id, outbox.attempts
                """,
                (max(1, lease_seconds), max(1, min(limit, 500)), owner),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_dispatched(self, job_id: str, dispatch_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE job_dispatch_outbox
                SET dispatched_at = NOW(),
                    dispatch_id = %s,
                    locked_at = NULL,
                    locked_by = NULL,
                    last_error = NULL
                WHERE job_id = %s
                """,
                (dispatch_id, job_id),
            )

    def mark_dispatch_failed(
        self,
        job_id: str,
        error: str,
        *,
        retry_seconds: int = 30,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE job_dispatch_outbox
                SET available_at = NOW() + make_interval(secs => %s),
                    locked_at = NULL,
                    locked_by = NULL,
                    last_error = %s
                WHERE job_id = %s
                  AND dispatched_at IS NULL
                """,
                (max(1, retry_seconds), error[:1000], job_id),
            )


def _parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _future_iso(seconds: int) -> str:
    from datetime import timedelta

    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def _validate_transition(current: str, requested: object) -> None:
    if requested is None or str(requested) == current:
        return
    target = str(requested)
    if target not in JOB_TRANSITIONS.get(current, set()):
        raise JobStoreError(f"invalid_job_transition:{current}:{target}")

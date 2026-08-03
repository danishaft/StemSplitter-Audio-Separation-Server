from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True)
class DispatchIntent:
    job_id: str
    tenant_id: str
    attempt_number: int = 1
    profile: str = "quality"
    priority: str = "medium"
    max_tenant_concurrency: int = 2

    @property
    def attempt_id(self) -> str:
        return f"{self.job_id}:attempt:{self.attempt_number}"

    @property
    def dispatch_key(self) -> str:
        return f"stem-separation:{self.attempt_id}"

    @property
    def concurrency_key(self) -> str:
        return f"tenant:{self.tenant_id}"

    def metadata(self) -> dict[str, Any]:
        return {
            "product_job_id": self.job_id,
            "attempt_id": self.attempt_id,
            "dispatch_key": self.dispatch_key,
            "tenant_id": self.tenant_id,
            "profile": self.profile,
            "priority": self.priority,
            "concurrency_key": self.concurrency_key,
            "max_tenant_concurrency": self.max_tenant_concurrency,
        }


class ContractLedger:
    """SQLite proof of the product-side invariants Hatchet must integrate with."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    terminal_event_id TEXT
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    attempt_number INTEGER NOT NULL,
                    dispatch_key TEXT NOT NULL UNIQUE,
                    external_run_id TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'queued',
                    UNIQUE(job_id, attempt_number)
                );
                CREATE TABLE IF NOT EXISTS dispatches (
                    dispatch_key TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                    external_run_id TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS callback_events (
                    callback_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    requested_status TEXT NOT NULL,
                    effective_status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS terminal_effects (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id),
                    attempt_id TEXT NOT NULL,
                    callback_id TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_effects (
                    idempotency_key TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    gpu_seconds REAL NOT NULL,
                    amount_microunits INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_key TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fault_claims (
                    fault_key TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS executions (
                    invocation_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    retry_count INTEGER NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL
                );
                """
            )

    def reserve_dispatch(
        self,
        intent: DispatchIntent,
        proposed_external_run_id: str,
    ) -> str:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT OR IGNORE INTO jobs(job_id, tenant_id)
                VALUES (?, ?)
                """,
                (intent.job_id, intent.tenant_id),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO attempts(
                    attempt_id, job_id, attempt_number, dispatch_key
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    intent.attempt_id,
                    intent.job_id,
                    intent.attempt_number,
                    intent.dispatch_key,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO dispatches(
                    dispatch_key, attempt_id, external_run_id
                ) VALUES (?, ?, ?)
                """,
                (
                    intent.dispatch_key,
                    intent.attempt_id,
                    proposed_external_run_id,
                ),
            )
            row = connection.execute(
                """
                SELECT external_run_id
                FROM dispatches
                WHERE dispatch_key = ?
                """,
                (intent.dispatch_key,),
            ).fetchone()
            if row is None:
                raise RuntimeError("dispatch_reservation_missing")
            external_run_id = str(row["external_run_id"])
            connection.execute(
                """
                UPDATE attempts
                SET external_run_id = ?
                WHERE attempt_id = ?
                """,
                (external_run_id, intent.attempt_id),
            )
            return external_run_id

    def request_cancel(self, job_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET cancel_requested = 1,
                    status = CASE
                        WHEN status IN ('completed', 'failed', 'cancelled')
                        THEN status
                        ELSE 'cancelling'
                    END
                WHERE job_id = ?
                """,
                (job_id,),
            )

    def apply_callback(
        self,
        *,
        callback_id: str,
        intent: DispatchIntent,
        status: str,
        artifact_key: str | None = None,
        gpu_seconds: float = 0.0,
        amount_microunits: int = 0,
    ) -> bool:
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"non_terminal_callback:{status}")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM callback_events WHERE callback_id = ?",
                (callback_id,),
            ).fetchone()
            if existing is not None:
                return False

            job = connection.execute(
                """
                SELECT status, cancel_requested, terminal_event_id
                FROM jobs
                WHERE job_id = ?
                """,
                (intent.job_id,),
            ).fetchone()
            if job is None:
                raise RuntimeError("job_missing_for_callback")

            effective_status = status
            if bool(job["cancel_requested"]) and status == "completed":
                effective_status = "cancelled"

            connection.execute(
                """
                INSERT INTO callback_events(
                    callback_id, attempt_id, requested_status, effective_status
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    callback_id,
                    intent.attempt_id,
                    status,
                    effective_status,
                ),
            )

            if job["terminal_event_id"] is not None:
                return False

            connection.execute(
                """
                UPDATE jobs
                SET status = ?, terminal_event_id = ?
                WHERE job_id = ? AND terminal_event_id IS NULL
                """,
                (effective_status, callback_id, intent.job_id),
            )
            connection.execute(
                """
                UPDATE attempts
                SET state = ?
                WHERE attempt_id = ?
                """,
                (effective_status, intent.attempt_id),
            )
            connection.execute(
                """
                INSERT INTO terminal_effects(
                    job_id, attempt_id, callback_id, status
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    intent.job_id,
                    intent.attempt_id,
                    callback_id,
                    effective_status,
                ),
            )

            if effective_status == "completed":
                if artifact_key:
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO artifacts(
                            artifact_key, job_id, attempt_id
                        ) VALUES (?, ?, ?)
                        """,
                        (artifact_key, intent.job_id, intent.attempt_id),
                    )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO usage_effects(
                        idempotency_key,
                        job_id,
                        attempt_id,
                        gpu_seconds,
                        amount_microunits
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        f"usage:{intent.attempt_id}",
                        intent.job_id,
                        intent.attempt_id,
                        gpu_seconds,
                        amount_microunits,
                    ),
                )
            return True

    def claim_fault(self, fault_key: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO fault_claims(fault_key) VALUES (?)",
                (fault_key,),
            )
            return cursor.rowcount == 1

    def record_execution_start(
        self,
        *,
        invocation_id: str,
        intent: DispatchIntent,
        retry_count: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO executions(
                    invocation_id,
                    attempt_id,
                    tenant_id,
                    retry_count,
                    started_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    invocation_id,
                    intent.attempt_id,
                    intent.tenant_id,
                    retry_count,
                    time.time(),
                ),
            )
            connection.execute(
                """
                UPDATE attempts
                SET state = 'running', retry_count = MAX(retry_count, ?)
                WHERE attempt_id = ?
                """,
                (retry_count, intent.attempt_id),
            )

    def record_execution_end(self, invocation_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE executions
                SET ended_at = ?
                WHERE invocation_id = ?
                """,
                (time.time(), invocation_id),
            )

    def count(self, table: str) -> int:
        allowed = {
            "artifacts",
            "attempts",
            "callback_events",
            "dispatches",
            "executions",
            "jobs",
            "terminal_effects",
            "usage_effects",
        }
        if table not in allowed:
            raise ValueError(f"unsupported_table:{table}")
        with self._connect() as connection:
            row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
            return int(row["count"])

    def value(self, query: str, parameters: tuple[Any, ...] = ()) -> Any:
        if not query.lstrip().upper().startswith("SELECT"):
            raise ValueError("read_queries_only")
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
            return None if row is None else row[0]


def run_with_bounded_retries(
    ledger: ContractLedger,
    intent: DispatchIntent,
    operation: Callable[[int], None],
    *,
    retries: int,
) -> int:
    if retries < 0:
        raise ValueError("retries_must_be_non_negative")

    for retry_count in range(retries + 1):
        invocation_id = f"{intent.attempt_id}:retry:{retry_count}"
        ledger.record_execution_start(
            invocation_id=invocation_id,
            intent=intent,
            retry_count=retry_count,
        )
        try:
            operation(retry_count)
        except RuntimeError:
            ledger.record_execution_end(invocation_id)
            if retry_count == retries:
                ledger.apply_callback(
                    callback_id=f"{intent.attempt_id}:failed",
                    intent=intent,
                    status="failed",
                )
                return retry_count
            continue

        ledger.record_execution_end(invocation_id)
        ledger.apply_callback(
            callback_id=f"{intent.attempt_id}:completed",
            intent=intent,
            status="completed",
            artifact_key=f"jobs/{intent.job_id}/stems.zip",
            gpu_seconds=12.5,
            amount_microunits=750,
        )
        return retry_count

    raise AssertionError("bounded_retry_loop_exhausted")

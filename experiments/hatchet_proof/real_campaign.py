from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from contract_ledger import ContractLedger, DispatchIntent
from hatchet_sdk import IdempotencyCollisionError, Priority
from hatchet_worker import SeparationInput, hatchet, separation_task

ROOT = Path(__file__).resolve().parents[2]
PROOF_ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "benchmarks" / "hatchet" / "real-campaign.json"
PROOF_DB = Path(os.environ.get("HATCHET_PROOF_DB", PROOF_ROOT / "real-proof.sqlite3"))


def make_input(
    suffix: str,
    *,
    tenant_id: str = "tenant_alpha",
    mode: str = "success",
    work_seconds: float = 0.3,
) -> tuple[DispatchIntent, SeparationInput]:
    intent = DispatchIntent(
        job_id=f"proof_{suffix}",
        tenant_id=tenant_id,
    )
    return intent, SeparationInput(
        job_id=intent.job_id,
        tenant_id=intent.tenant_id,
        attempt_number=intent.attempt_number,
        dispatch_key=intent.dispatch_key,
        mode=mode,
        work_seconds=work_seconds,
    )


@contextmanager
def worker_process(slots: int) -> Iterator[subprocess.Popen[str]]:
    environment = {
        **os.environ,
        "HATCHET_PROOF_DB": str(PROOF_DB),
        "HATCHET_PROOF_WORKER_SLOTS": str(slots),
    }
    process = subprocess.Popen(
        [sys.executable, str(PROOF_ROOT / "hatchet_worker.py")],
        cwd=PROOF_ROOT,
        env=environment,
        text=True,
    )
    time.sleep(2)
    try:
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def reserve_and_run(
    ledger: ContractLedger,
    intent: DispatchIntent,
    payload: SeparationInput,
    *,
    priority: Priority = Priority.MEDIUM,
):
    reference = separation_task.run(
        input=payload,
        priority=priority,
        additional_metadata=intent.metadata(),
        wait_for_result=False,
    )
    ledger.reserve_dispatch(intent, reference.workflow_run_id)
    return reference


def main() -> int:
    if PROOF_DB.exists():
        PROOF_DB.unlink()
    ledger = ContractLedger(PROOF_DB)
    checks: dict[str, bool] = {}

    with worker_process(slots=4):
        intent, payload = make_input("idempotency", work_seconds=1.0)
        first = reserve_and_run(ledger, intent, payload)
        collision_run_id = ""
        try:
            second = separation_task.run(
                input=payload,
                priority=Priority.MEDIUM,
                additional_metadata=intent.metadata(),
                wait_for_result=False,
            )
            collision_run_id = second.workflow_run_id
        except IdempotencyCollisionError as exc:
            collision_run_id = exc.existing_run_external_id
        first.result()
        checks["idempotent_dispatch"] = (
            first.workflow_run_id == collision_run_id
            and ledger.count("dispatches") == 1
        )

        retry_intent, retry_payload = make_input(
            "retry",
            mode="fail_once",
        )
        retry_ref = reserve_and_run(ledger, retry_intent, retry_payload)
        retry_ref.result()
        checks["bounded_retry"] = (
            ledger.value(
                """
                SELECT MAX(retry_count)
                FROM executions
                WHERE attempt_id = ?
                """,
                (retry_intent.attempt_id,),
            )
            == 1
        )

        cancel_intent, cancel_payload = make_input(
            "cancel",
            work_seconds=10.0,
        )
        cancel_ref = reserve_and_run(ledger, cancel_intent, cancel_payload)
        time.sleep(0.5)
        ledger.request_cancel(cancel_intent.job_id)
        hatchet.runs.cancel(cancel_ref.workflow_run_id)
        try:
            cancel_ref.result()
        except (RuntimeError, ValueError):
            pass
        ledger.apply_callback(
            callback_id=f"{cancel_intent.attempt_id}:cancelled",
            intent=cancel_intent,
            status="cancelled",
        )
        checks["cancellation"] = (
            ledger.value(
                "SELECT status FROM jobs WHERE job_id = ?",
                (cancel_intent.job_id,),
            )
            == "cancelled"
        )

        concurrency_refs = []
        concurrency_intents = []
        for index in range(5):
            concurrent_intent, concurrent_payload = make_input(
                f"concurrency_{index}",
                work_seconds=0.8,
            )
            concurrency_intents.append(concurrent_intent)
            concurrency_refs.append(
                reserve_and_run(
                    ledger,
                    concurrent_intent,
                    concurrent_payload,
                )
            )
        for reference in concurrency_refs:
            reference.result()
        checks["tenant_concurrency"] = verify_max_concurrency(
            ledger,
            [intent.attempt_id for intent in concurrency_intents],
            maximum=2,
        )

    with worker_process(slots=1):
        blocker_intent, blocker_payload = make_input(
            "priority_blocker",
            work_seconds=1.5,
        )
        blocker_ref = reserve_and_run(
            ledger,
            blocker_intent,
            blocker_payload,
            priority=Priority.HIGH,
        )
        time.sleep(0.3)
        low_intent, low_payload = make_input("priority_low")
        high_intent, high_payload = make_input("priority_high")
        low_ref = reserve_and_run(
            ledger,
            low_intent,
            low_payload,
            priority=Priority.LOW,
        )
        high_ref = reserve_and_run(
            ledger,
            high_intent,
            high_payload,
            priority=Priority.HIGH,
        )
        blocker_ref.result()
        high_ref.result()
        low_ref.result()
        high_started = ledger.value(
            "SELECT MIN(started_at) FROM executions WHERE attempt_id = ?",
            (high_intent.attempt_id,),
        )
        low_started = ledger.value(
            "SELECT MIN(started_at) FROM executions WHERE attempt_id = ?",
            (low_intent.attempt_id,),
        )
        checks["priority_order"] = bool(high_started < low_started)

    crash_intent, crash_payload = make_input("crash", mode="crash_once")
    with worker_process(slots=1) as crashing_worker:
        crash_ref = reserve_and_run(ledger, crash_intent, crash_payload)
        crashing_worker.wait(timeout=20)
        if crashing_worker.returncode != 86:
            raise RuntimeError(
                f"worker_did_not_crash_as_expected:{crashing_worker.returncode}"
            )
    with worker_process(slots=1):
        crash_ref.result()
    checks["worker_crash_recovery"] = (
        ledger.value(
            "SELECT status FROM jobs WHERE job_id = ?",
            (crash_intent.job_id,),
        )
        == "completed"
    )

    checks["zero_duplicate_terminal_effects"] = (
        ledger.count("terminal_effects") == ledger.count("jobs")
    )
    checks["zero_duplicate_economic_effects"] = (
        ledger.value(
            """
            SELECT COUNT(*)
            FROM (
                SELECT job_id
                FROM usage_effects
                GROUP BY job_id
                HAVING COUNT(*) > 1
            )
            """
        )
        == 0
    )

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hatchet_source_commit": "41b056313b43",
        "hatchet_version": "v0.98.7",
        "sdk_version": "1.37.0",
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "counts": {
            table: ledger.count(table)
            for table in (
                "jobs",
                "attempts",
                "dispatches",
                "executions",
                "callback_events",
                "terminal_effects",
                "usage_effects",
                "artifacts",
            )
        },
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


def verify_max_concurrency(
    ledger: ContractLedger,
    attempt_ids: list[str],
    *,
    maximum: int,
) -> bool:
    placeholders = ",".join("?" for _ in attempt_ids)
    with ledger._connect() as connection:
        rows = connection.execute(
            f"""
            SELECT started_at, ended_at
            FROM executions
            WHERE attempt_id IN ({placeholders})
            """,
            tuple(attempt_ids),
        ).fetchall()
    events: list[tuple[float, int]] = []
    for row in rows:
        if row["ended_at"] is None:
            return False
        events.append((float(row["started_at"]), 1))
        events.append((float(row["ended_at"]), -1))
    active = 0
    peak = 0
    for _timestamp, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        peak = max(peak, active)
    return peak <= maximum


if __name__ == "__main__":
    raise SystemExit(main())

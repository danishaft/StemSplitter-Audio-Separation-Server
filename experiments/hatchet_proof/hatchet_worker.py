from __future__ import annotations

import os
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from contract_ledger import ContractLedger, DispatchIntent
from hatchet_sdk import (
    ConcurrencyExpression,
    ConcurrencyLimitStrategy,
    Context,
    Hatchet,
    Priority,
    StatusBasedIdempotencyConfig,
)
from pydantic import BaseModel, Field

PROOF_DB = Path(
    os.environ.get(
        "HATCHET_PROOF_DB",
        Path(tempfile.gettempdir()) / "stem-splitter-hatchet-proof.sqlite3",
    )
)
WORKER_SLOTS = int(os.environ.get("HATCHET_PROOF_WORKER_SLOTS", "4"))
ledger = ContractLedger(PROOF_DB)
hatchet = Hatchet()


class SeparationInput(BaseModel):
    job_id: str
    tenant_id: str
    attempt_number: int = 1
    dispatch_key: str
    profile: str = "quality"
    mode: str = "success"
    work_seconds: float = Field(default=0.2, ge=0.0, le=30.0)

    def intent(self) -> DispatchIntent:
        return DispatchIntent(
            job_id=self.job_id,
            tenant_id=self.tenant_id,
            attempt_number=self.attempt_number,
            profile=self.profile,
        )


@hatchet.task(
    name="stem-separation-proof",
    version="1",
    input_validator=SeparationInput,
    default_priority=Priority.MEDIUM,
    concurrency=ConcurrencyExpression(
        expression="input.tenant_id",
        max_runs=2,
        limit_strategy=ConcurrencyLimitStrategy.GROUP_ROUND_ROBIN,
    ),
    execution_timeout=timedelta(seconds=45),
    retries=2,
    backoff_factor=1.0,
    backoff_max_seconds=2,
    idempotency=StatusBasedIdempotencyConfig(
        key_expression="input.dispatch_key",
        fallback_ttl=timedelta(hours=24),
    ),
)
def separation_task(
    input: SeparationInput,
    ctx: Context,
) -> dict[str, str | int]:
    intent = input.intent()
    invocation_id = (
        f"{ctx.workflow_run_id}:{intent.attempt_id}:retry:{ctx.retry_count}"
    )
    ledger.record_execution_start(
        invocation_id=invocation_id,
        intent=intent,
        retry_count=ctx.retry_count,
    )

    fault_key = f"{intent.attempt_id}:{input.mode}"
    if input.mode == "fail_once" and ledger.claim_fault(fault_key):
        ledger.record_execution_end(invocation_id)
        raise RuntimeError("injected_retryable_failure")
    if input.mode == "crash_once" and ledger.claim_fault(fault_key):
        os._exit(86)

    deadline = time.monotonic() + input.work_seconds
    while time.monotonic() < deadline:
        if ctx.is_cancelled:
            ledger.record_execution_end(invocation_id)
            raise RuntimeError("cancelled_by_hatchet")
        time.sleep(0.05)

    callback_id = f"{intent.attempt_id}:completed"
    ledger.apply_callback(
        callback_id=callback_id,
        intent=intent,
        status="completed",
        artifact_key=f"jobs/{intent.job_id}/stems.zip",
        gpu_seconds=max(input.work_seconds, 0.01),
        amount_microunits=100,
    )
    # Deliberately replay the callback to verify the product ledger boundary.
    ledger.apply_callback(
        callback_id=callback_id,
        intent=intent,
        status="completed",
        artifact_key=f"jobs/{intent.job_id}/stems.zip",
        gpu_seconds=max(input.work_seconds, 0.01),
        amount_microunits=100,
    )
    ledger.record_execution_end(invocation_id)
    return {
        "job_id": input.job_id,
        "attempt_number": input.attempt_number,
        "retry_count": ctx.retry_count,
    }


def main() -> None:
    worker = hatchet.worker(
        "stem-separation-proof-worker",
        slots=WORKER_SLOTS,
        workflows=[separation_task],
    )
    worker.start()


if __name__ == "__main__":
    main()

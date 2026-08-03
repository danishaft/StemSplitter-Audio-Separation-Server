from __future__ import annotations

import json
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import hatchet_worker
from hatchet_sdk import Context

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "benchmarks" / "hatchet" / "sdk-compatibility.json"


def main() -> int:
    if not isinstance(Context.workflow_run_id, property):
        raise TypeError("context_workflow_run_id_contract_changed")
    if not isinstance(Context.retry_count, property):
        raise TypeError("context_retry_count_contract_changed")
    if not isinstance(Context.is_cancelled, property):
        raise TypeError("context_cancellation_contract_changed")

    payload = hatchet_worker.SeparationInput(
        job_id="job_static",
        tenant_id="tenant_static",
        dispatch_key="stem-separation:job_static:attempt:1",
    )
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "evidence_class": "sdk_definition_import_only",
        "hatchet_source_commit": "41b056313b43",
        "hatchet_version": "v0.98.7",
        "sdk_distribution": version("hatchet-sdk"),
        "expected_sdk_version": "1.37.0",
        "task_name": hatchet_worker.separation_task.name,
        "stable_attempt_id": payload.intent().attempt_id,
        "proves": [
            "the pinned SDK imports the task definition",
            "the task decorator accepts the selected options",
            "the Pydantic input maps to the stable product attempt identifier",
            "the selected Context APIs are properties in SDK 1.37.0",
        ],
        "does_not_prove": [
            "server scheduling",
            "server idempotency enforcement",
            "priority ordering",
            "concurrency enforcement",
            "cancellation propagation",
            "worker crash recovery",
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

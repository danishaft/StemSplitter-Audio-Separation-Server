from __future__ import annotations

from datetime import datetime, timezone

import pytest

from splitter.job_store import JsonJobStore, JobStoreError


def _payload(job_id: str) -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "job_id": job_id,
        "profile": "quality_gpu_experimental",
        "status": "queued",
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _create(store: JsonJobStore, job_id: str, owner_id: str = "artist-1"):
    return store.create(
        _payload(job_id),
        owner_id=owner_id,
        idempotency_key=None,
        max_active=10,
        max_active_per_owner=5,
    )


def test_admission_is_enforced_by_the_job_store(tmp_path):
    store = JsonJobStore(tmp_path)
    _create(store, "job-1")

    with pytest.raises(JobStoreError, match="owner_job_capacity_exceeded"):
        store.create(
            _payload("job-2"),
            owner_id="artist-1",
            idempotency_key=None,
            max_active=10,
            max_active_per_owner=1,
        )


def test_running_cancellation_is_truthful_and_evented(tmp_path):
    store = JsonJobStore(tmp_path)
    _create(store, "job-1")
    store.update("job-1", {"status": "running", "stage": "gpu_worker_running"})

    cancelled = store.request_cancel("job-1")

    assert cancelled is not None
    assert cancelled["status"] == "cancelling"
    assert cancelled["cancel_requested"] is True
    events = store.list_events("job-1")
    assert [event["id"] for event in events] == list(range(1, len(events) + 1))
    assert events[-1]["payload"]["status"] == "cancelling"


def test_terminal_job_deletion_removes_local_state(tmp_path):
    store = JsonJobStore(tmp_path)
    _create(store, "job-1")

    assert store.get("job-1")["status"] == "queued"
    store.update("job-1", {"status": "cancelled", "stage": "cancelled"})
    assert store.delete("job-1") is True
    assert store.get("job-1") is None

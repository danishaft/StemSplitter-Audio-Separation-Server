from __future__ import annotations

from pathlib import Path
from typing import Any

from splitter import jobs


class JobSubmissionError(RuntimeError):
    """Raised after a newly persisted job cannot be dispatched."""


class JobService:
    """Coordinates job persistence and dispatch as one application operation."""

    def create_upload(
        self,
        upload_name: str,
        file_bytes: bytes,
        *,
        profile: str,
        owner_id: str,
        idempotency_key: str | None,
        input_source: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        status = jobs.create_job(
            upload_name,
            file_bytes,
            profile=profile,
            input_source=input_source,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
        )
        return self._dispatch_new_job(status)

    def create_object(
        self,
        upload_name: str,
        object_reference: dict[str, object],
        *,
        profile: str,
        owner_id: str,
        idempotency_key: str | None,
        input_source: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        status = jobs.create_job_from_object(
            upload_name,
            object_reference,
            profile=profile,
            input_source=input_source,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
        )
        return self._dispatch_new_job(status)

    def create_local_file(
        self,
        upload_name: str,
        source_path: Path,
        *,
        profile: str,
        owner_id: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        status = jobs.create_job_from_path(
            upload_name,
            source_path,
            profile=profile,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
        )
        return self._dispatch_new_job(status)

    @staticmethod
    def _dispatch_new_job(status: dict[str, Any]) -> dict[str, Any]:
        if status.get("idempotency_replayed"):
            return status
        job_id = str(status["job_id"])
        try:
            jobs.submit_job(job_id)
        except Exception as exc:
            jobs.record_dispatch_failure(job_id, exc)
            raise JobSubmissionError("job_dispatch_failed") from exc
        return status


job_service = JobService()

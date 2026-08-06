from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from splitter import jobs
from splitter.application import job_service
from splitter.auth import Principal
from splitter.config import ALLOW_MULTIPART_UPLOADS, MAX_CONTENT_LENGTH
from splitter.infrastructure.job_store import JobStoreError
from splitter.infrastructure.object_storage import (
    ObjectStorageError,
    object_store_from_config,
)
from splitter.sources import AudiusClient, AudiusError

from ..dependencies import current_principal, idempotency_key
from ..responses import error_response
from ..schemas import (
    CreateAudiusJobRequest,
    CreateObjectJobRequest,
    JobEventsResponse,
    JobResponse,
)
from ..services import allowed_file, artifact_payload, owned_job, requested_profile
from ..uploading import UploadTooLargeError, stream_upload_to_temp

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _accepted(status: dict[str, Any]) -> dict[str, Any]:
    response = dict(status)
    response["artifacts"] = {}
    return response


def _public_artifact_metadata(
    manifest: dict[str, object] | None,
) -> dict[str, dict[str, dict[str, object]]]:
    if not manifest:
        return {}
    result: dict[str, dict[str, dict[str, object]]] = {}
    for manifest_key, response_key in (
        ("published_main_stems", "main_stems"),
        ("published_broad_stems", "broad_stems"),
        ("published_derived_stems", "derived_stems"),
        ("published_specialist_substems", "specialist_substems"),
    ):
        group = manifest.get(manifest_key)
        if not isinstance(group, dict):
            continue
        public_group: dict[str, dict[str, object]] = {}
        for name, payload in group.items():
            if not isinstance(payload, dict):
                continue
            public_group[str(name)] = {
                key: payload[key]
                for key in (
                    "artifact_group",
                    "publish_reason",
                    "publish_status",
                    "quality_score",
                    "source_model",
                    "warnings",
                )
                if key in payload
            }
        if public_group:
            result[response_key] = public_group
    return result


async def _json_payload(request: Request) -> dict[str, Any] | None:
    body = await request.body()
    if len(body) > MAX_CONTENT_LENGTH:
        return None
    try:
        payload = await request.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


@router.post(
    "",
    status_code=202,
    operation_id="createJob",
    response_model=JobResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/CreateObjectJobRequest"},
                            {"$ref": "#/components/schemas/CreateAudiusJobRequest"},
                        ]
                    }
                },
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                            "profile": {"type": "string"},
                        },
                    }
                },
            },
        }
    },
)
async def create_job_route(
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
    request_idempotency_key: Annotated[str | None, Depends(idempotency_key)],
):
    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("application/json"):
        payload = await _json_payload(request)
        if payload is None:
            return error_response(400, "invalid_json")
        if isinstance(payload.get("input"), dict):
            return _create_object_job(
                payload,
                principal,
                request_idempotency_key,
            )
        return _create_audius_job(
            payload,
            principal,
            request_idempotency_key,
        )

    form = await request.form()
    if not ALLOW_MULTIPART_UPLOADS:
        return error_response(415, "direct_upload_required")
    audio_file = form.get("file")
    if not isinstance(audio_file, UploadFile):
        return error_response(400, "No audio file in request")
    if not audio_file.filename:
        return error_response(400, "No file selected")
    if not allowed_file(audio_file.filename):
        return error_response(
            400,
            "Invalid format. Use MP3, WAV, FLAC, OGG, or M4A.",
        )
    try:
        profile = requested_profile(form.get("profile"))
    except ValueError:
        return error_response(400, "unsupported_profile")
    try:
        upload_path = await stream_upload_to_temp(
            audio_file,
            max_bytes=MAX_CONTENT_LENGTH,
        )
    except UploadTooLargeError:
        return error_response(413, "request_too_large")
    try:
        status = job_service.create_local_file(
            audio_file.filename,
            upload_path,
            profile=profile,
            owner_id=principal.subject,
            idempotency_key=request_idempotency_key,
        )
    finally:
        upload_path.unlink(missing_ok=True)
    return _accepted(status)


def _create_object_job(
    payload: dict[str, Any],
    principal: Principal,
    request_idempotency_key: str | None,
):
    try:
        parsed = CreateObjectJobRequest.model_validate(payload)
    except ValidationError:
        return error_response(400, "invalid_object_input")
    filename = parsed.input.filename.strip()
    object_reference = parsed.input.object.model_dump()
    if not filename or not allowed_file(filename):
        return error_response(400, "invalid_object_input")
    try:
        profile = requested_profile(parsed.profile)
        if principal.subject != "local-development":
            store = object_store_from_config()
            if store is None:
                raise ObjectStorageError("object_storage_not_configured")
            store.validate_input_owner(object_reference, principal.subject)
        status = job_service.create_object(
            filename,
            object_reference,
            profile=profile,
            input_source={"type": "upload", "provider": "object_storage"},
            owner_id=principal.subject,
            idempotency_key=request_idempotency_key,
        )
    except ObjectStorageError:
        return error_response(400, "invalid_object_input")
    except ValueError:
        return error_response(400, "unsupported_profile")
    return _accepted(status)


def _create_audius_job(
    payload: dict[str, Any],
    principal: Principal,
    request_idempotency_key: str | None,
):
    try:
        parsed = CreateAudiusJobRequest.model_validate(payload)
    except ValidationError:
        source = payload.get("source")
        if not isinstance(source, dict) or source.get("provider") != "audius":
            return error_response(400, "invalid_source")
        return error_response(400, "invalid_track_id")
    try:
        profile = requested_profile(parsed.profile)
    except ValueError:
        return error_response(400, "unsupported_profile")
    try:
        imported = AudiusClient().download(parsed.source.track_id)
    except AudiusError as exc:
        return error_response(exc.status_code, exc.code)
    status = job_service.create_upload(
        imported.filename,
        imported.content,
        profile=profile,
        input_source=imported.source,
        owner_id=principal.subject,
        idempotency_key=request_idempotency_key,
    )
    return _accepted(status)


@router.get("/{job_id}", operation_id="getJob", response_model=JobResponse)
def job_status(
    job_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
):
    status = owned_job(job_id, principal.subject)
    if not status:
        return error_response(404, "Job not found")
    response = dict(status)
    manifest = jobs.get_manifest(job_id)
    response["artifacts"] = artifact_payload(job_id, manifest)
    response["artifact_metadata"] = _public_artifact_metadata(manifest)
    if manifest:
        response["rejected_candidates"] = manifest.get("rejected_candidates", {})
        response["missing_features"] = manifest.get("missing_features", [])
        response["remote_adapter_status"] = manifest.get("remote_adapter_status")
        response["remote_adapter_reason"] = manifest.get("remote_adapter_reason")
        response["stem_contract"] = manifest.get("stem_contract", {})
        response["unit_economics"] = manifest.get("unit_economics", {})
    return response


@router.get(
    "/{job_id}/events",
    operation_id="getJobEvents",
    response_model=JobEventsResponse,
)
def job_events(
    job_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
    after: str = "0",
    limit: str = "100",
):
    if owned_job(job_id, principal.subject) is None:
        return error_response(404, "Job not found")
    try:
        after_id = int(after)
        event_limit = int(limit)
    except ValueError:
        return error_response(400, "invalid_pagination")
    events = jobs.get_job_events(
        job_id,
        after_id=after_id,
        limit=event_limit,
    )
    next_after = int(events[-1]["id"]) if events else max(0, after_id)
    return {"events": events, "next_after": next_after}


@router.post(
    "/{job_id}/resume",
    status_code=202,
    operation_id="resumeJob",
    response_model=JobResponse,
)
def resume_job(
    job_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
):
    if owned_job(job_id, principal.subject) is None:
        return error_response(404, "Job not found")
    status = jobs.resume_remote_job(job_id)
    if status is None:
        return error_response(409, "job_not_resumable")
    return status


@router.post(
    "/{job_id}/cancel",
    status_code=202,
    operation_id="cancelJob",
    response_model=JobResponse,
)
def cancel_job_route(
    job_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
):
    if owned_job(job_id, principal.subject) is None:
        return error_response(404, "Job not found")
    status = jobs.cancel_job(job_id)
    if status is None:
        return error_response(404, "Job not found")
    return status


@router.delete("/{job_id}", status_code=204, operation_id="deleteJob")
def delete_job_route(
    job_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
):
    if owned_job(job_id, principal.subject) is None:
        return error_response(404, "Job not found")
    try:
        deleted = jobs.delete_job(job_id)
    except JobStoreError as exc:
        if str(exc) == "job_not_terminal":
            return error_response(409, "job_not_terminal")
        raise
    if not deleted:
        return error_response(404, "Job not found")
    return Response(status_code=204)


@router.get("/{job_id}/manifest", operation_id="getJobManifest")
def job_manifest(
    job_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
):
    if owned_job(job_id, principal.subject) is None:
        return error_response(404, "Job not found")
    manifest = jobs.get_manifest(job_id)
    if not manifest:
        return error_response(404, "Manifest not found")
    return manifest

from __future__ import annotations

import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from splitter.auth import Principal
from splitter.path_safety import resolve_artifact_path

from ..dependencies import current_principal
from ..responses import error_response
from ..services import job_root, owned_job

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("/{job_id}/{artifact_path:path}", operation_id="getArtifact")
def serve_artifact(
    job_id: str,
    artifact_path: str,
    principal: Annotated[Principal, Depends(current_principal)],
):
    if owned_job(job_id, principal.subject) is None:
        return error_response(404, "Artifact not found")
    root = job_root(job_id)
    try:
        target = resolve_artifact_path(root, artifact_path)
    except ValueError:
        return error_response(404, "Artifact not found")
    if not target.is_file():
        return error_response(404, "Artifact not found")
    media_type, _ = mimetypes.guess_type(target.name)
    return FileResponse(
        target,
        media_type=media_type or "application/octet-stream",
        headers={"Cache-Control": "no-cache"},
    )

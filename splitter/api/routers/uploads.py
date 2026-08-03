from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from splitter.auth import Principal
from splitter.infrastructure.object_storage import (
    ObjectStorageError,
    object_store_from_config,
)

from ..dependencies import current_principal
from ..responses import error_response
from ..schemas import DirectUploadRequest, DirectUploadResponse
from ..services import allowed_file, content_type_for

router = APIRouter(tags=["uploads"])


@router.post(
    "/uploads",
    status_code=201,
    operation_id="createDirectUpload",
    response_model=DirectUploadResponse,
)
def create_direct_upload(
    payload: DirectUploadRequest,
    principal: Annotated[Principal, Depends(current_principal)],
):
    filename = payload.filename.strip()
    if not filename or not allowed_file(filename):
        return error_response(400, "invalid_filename")
    try:
        store = object_store_from_config()
        if store is None:
            return error_response(503, "direct_upload_unavailable")
        content_type = content_type_for(filename, payload.content_type)
        if principal.subject == "local-development":
            grant = store.create_upload(filename, content_type)
        else:
            grant = store.create_upload(
                filename,
                content_type,
                owner_id=principal.subject,
            )
    except ObjectStorageError:
        return error_response(503, "object_storage_error")
    return {**grant, "filename": Path(filename).name}

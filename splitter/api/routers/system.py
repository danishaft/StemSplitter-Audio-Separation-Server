from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response

from splitter.config import APP_ENV, APP_VERSION
from splitter.jobs import control_plane_health

from ..schemas import CapabilitiesResponse
from ..services import capabilities_payload

router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
def index() -> dict[str, str]:
    return {
        "service": "StemSplitter API",
        "version": APP_VERSION,
        "docs": "/docs",
    }


@router.get(
    "/capabilities",
    operation_id="getCapabilities",
    response_model=CapabilitiesResponse,
)
def capabilities() -> dict[str, object]:
    return capabilities_payload()


@router.get("/health/live", operation_id="getLiveness")
def live() -> dict[str, str]:
    return {"status": "ok", "version": APP_VERSION}


@router.get("/health/version", operation_id="getVersion")
def version() -> dict[str, str]:
    return {"version": APP_VERSION, "environment": APP_ENV}


@router.get("/health/ready", operation_id="getReadiness", response_model=None)
def ready() -> dict[str, str]:
    return {"status": "ready", "version": APP_VERSION}


@router.get("/health/dependencies", operation_id="getDependencyHealth", response_model=None)
def dependencies() -> Response | dict[str, object]:
    try:
        dependency_status = control_plane_health()
    except Exception:
        from ..responses import error_response

        return error_response(503, "not_ready")
    ready_state = all(dependency_status.values())
    payload = {
        "status": "ready" if ready_state else "not_ready",
        "dependencies": dependency_status,
    }
    if ready_state:
        return payload
    return JSONResponse(payload, status_code=503)

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from pydantic.json_schema import models_json_schema
from starlette.middleware.trustedhost import TrustedHostMiddleware

from splitter.application import JobSubmissionError
from splitter.auth import AuthError
from splitter.bootstrap import shutdown_runtime_services
from splitter.config import (
    APP_ENV,
    APP_VERSION,
    AUTH_MODE,
    CORS_ALLOWED_ORIGINS,
    TRUSTED_HOSTS,
)
from splitter.infrastructure.job_store import JobStoreError
from splitter.observability import (
    configure_error_reporting,
    configure_logging,
    instrument_fastapi,
)
from splitter.runtime import validate_runtime_config

from .observability import (
    ContentLengthLimitMiddleware,
    EdgePolicyMiddleware,
    RequestContextMiddleware,
)
from .observability import (
    router as observability_router,
)
from .responses import APIError, error_response
from .routers import artifacts, jobs, sources, system, uploads
from .schemas import CreateAudiusJobRequest, CreateObjectJobRequest
from .services import FRONTEND_DIST_DIR


def create_app() -> FastAPI:
    configure_logging(APP_ENV)
    configure_error_reporting()
    validate_runtime_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        del app
        yield
        shutdown_runtime_services()

    app = FastAPI(
        title="StemSplitter API",
        version=APP_VERSION,
        description="Asynchronous music source-separation control plane.",
        lifespan=lifespan,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(TRUSTED_HOSTS))
    app.add_middleware(EdgePolicyMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(ContentLengthLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(CORS_ALLOWED_ORIGINS),
        allow_credentials=AUTH_MODE == "jwt",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError):
        del request
        return error_response(exc.status_code, exc.code)

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        del request
        return error_response(exc.status_code, exc.error, exc.message)

    @app.exception_handler(JobStoreError)
    async def job_store_error_handler(request: Request, exc: JobStoreError):
        del request
        code = str(exc)
        if code in {"job_capacity_exceeded", "owner_job_capacity_exceeded"}:
            return error_response(
                503,
                code,
                "Job capacity is currently full.",
            )
        return error_response(503, "job_store_error", code)

    @app.exception_handler(JobSubmissionError)
    async def job_submission_error_handler(request: Request, exc: JobSubmissionError):
        del request, exc
        return error_response(
            503,
            "job_dispatch_failed",
            "The job was persisted but could not be queued.",
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        del request, exc
        return error_response(422, "invalid_request")

    app.include_router(observability_router)
    app.include_router(sources.router)
    app.include_router(uploads.router)
    app.include_router(jobs.router)
    app.include_router(artifacts.router)
    app.include_router(system.router)
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST_DIR / "assets", check_dir=False),
        name="assets",
    )

    def custom_openapi():
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        _, request_schemas = models_json_schema(
            [
                (CreateObjectJobRequest, "validation"),
                (CreateAudiusJobRequest, "validation"),
            ],
            ref_template="#/components/schemas/{model}",
        )
        schema.setdefault("components", {}).setdefault("schemas", {}).update(
            request_schemas.get("$defs", {})
        )
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi
    instrument_fastapi(app)
    return app

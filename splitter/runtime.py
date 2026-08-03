from __future__ import annotations

from .config import (
    APP_ENV,
    APPLICATIONINSIGHTS_CONNECTION_STRING,
    AUTH_AUDIENCE,
    AUTH_ISSUER,
    AUTH_JWKS_URL,
    AUTH_MODE,
    CORS_ALLOWED_ORIGINS,
    DATABASE_URL,
    EDGE_MODE,
    EDGE_VERIFY_SECRET,
    GPU_WORKER_CONFIG,
    JOB_DISPATCH_BACKEND,
    JOB_LEASE_RENEW_INTERVAL,
    JOB_LEASE_SECONDS,
    JOB_STORE_BACKEND,
    METRICS_BEARER_TOKEN,
    OBJECT_STORAGE_CONFIG,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    PUBLIC_API_URL,
    RATE_LIMIT_ENABLED,
    REDIS_URL,
    SENTRY_DSN,
    TRUSTED_HOSTS,
)


class RuntimeConfigurationError(RuntimeError):
    """Raised when a production process would start with unsafe fallbacks."""


def validate_runtime_config() -> None:
    if APP_ENV not in {"development", "test", "production"}:
        raise RuntimeConfigurationError("invalid_app_env")
    if APP_ENV != "production":
        return
    failures: list[str] = []
    if JOB_STORE_BACKEND != "postgres" or not DATABASE_URL:
        failures.append("postgres_job_store_required")
    if JOB_DISPATCH_BACKEND != "rq" or not REDIS_URL:
        failures.append("redis_rq_dispatch_required")
    if OBJECT_STORAGE_CONFIG.get("backend") != "s3" or not all(
        (
            OBJECT_STORAGE_CONFIG.get("bucket"),
            OBJECT_STORAGE_CONFIG.get("endpoint_url"),
            OBJECT_STORAGE_CONFIG.get("access_key_id"),
            OBJECT_STORAGE_CONFIG.get("secret_access_key"),
        )
    ):
        failures.append("private_object_storage_required")
    if AUTH_MODE != "jwt" or not all((AUTH_JWKS_URL, AUTH_ISSUER, AUTH_AUDIENCE)):
        failures.append("jwt_authentication_required")
    if not CORS_ALLOWED_ORIGINS or "*" in CORS_ALLOWED_ORIGINS:
        failures.append("explicit_cors_origins_required")
    if not TRUSTED_HOSTS or "*" in TRUSTED_HOSTS:
        failures.append("explicit_trusted_hosts_required")
    if EDGE_MODE != "cloudflare" or len(EDGE_VERIFY_SECRET) < 32:
        failures.append("cloudflare_edge_verification_required")
    if not RATE_LIMIT_ENABLED:
        failures.append("rate_limiting_required")
    if not METRICS_BEARER_TOKEN:
        failures.append("metrics_authentication_required")
    if not PUBLIC_API_URL.startswith("https://"):
        failures.append("https_public_api_url_required")
    if not (
        SENTRY_DSN
        or OTEL_EXPORTER_OTLP_ENDPOINT
        or APPLICATIONINSIGHTS_CONNECTION_STRING
    ):
        failures.append("production_telemetry_required")
    if not all((GPU_WORKER_CONFIG.get("base_url"), GPU_WORKER_CONFIG.get("api_key"))):
        failures.append("gpu_worker_required")
    if JOB_LEASE_RENEW_INTERVAL >= JOB_LEASE_SECONDS:
        failures.append("job_lease_renewal_must_precede_expiry")
    if failures:
        raise RuntimeConfigurationError(",".join(failures))

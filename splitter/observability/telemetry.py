from __future__ import annotations

import logging

from splitter.config import (
    APP_ENV,
    APP_VERSION,
    APPLICATIONINSIGHTS_CONNECTION_STRING,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_SERVICE_NAME,
    SENTRY_DSN,
    SENTRY_TRACES_SAMPLE_RATE,
)

logger = logging.getLogger("stemsplitter.telemetry")


def configure_error_reporting() -> None:
    if APPLICATIONINSIGHTS_CONNECTION_STRING:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor
        except ImportError as exc:  # pragma: no cover - production dependency
            raise RuntimeError("azure_monitor_dependency_not_installed") from exc
        configure_azure_monitor(
            connection_string=APPLICATIONINSIGHTS_CONNECTION_STRING,
            enable_live_metrics=True,
        )
    if not SENTRY_DSN:
        return
    try:
        import sentry_sdk
    except ImportError as exc:  # pragma: no cover - production dependency
        raise RuntimeError("sentry_sdk_not_installed") from exc
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=APP_ENV,
        release=APP_VERSION,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
    )


def instrument_fastapi(app: object) -> None:
    if not OTEL_EXPORTER_OTLP_ENDPOINT:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:  # pragma: no cover - production dependency
        raise RuntimeError("opentelemetry_dependencies_not_installed") from exc

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": OTEL_SERVICE_NAME,
                "service.version": APP_VERSION,
                "deployment.environment": APP_ENV,
            }
        )
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/") + "/v1/traces")
        )
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health/live,health/ready,metrics",
    )
    logger.info("otel_instrumentation_enabled service=%s", OTEL_SERVICE_NAME)

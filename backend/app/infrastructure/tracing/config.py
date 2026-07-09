"""Central OpenTelemetry tracing configuration.

Application code should call ``configure_tracing`` at process startup and use
``business_span`` / ``get_tracer`` for manual spans. Tracer providers must not
be constructed outside this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from backend.app.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy import Engine

    from backend.app.infrastructure.config.settings import Settings

logger = get_logger(__name__)

_initialized = False
_redis_instrumented = False
_kafka_instrumented = False


def configure_tracing(
    settings: Settings,
    *,
    service_name: str,
) -> TracerProvider | None:
    """Initialize global tracing for the current process when enabled."""
    global _initialized

    if not settings.otel_enabled:
        return None

    if _initialized:
        provider = trace.get_tracer_provider()
        return provider if isinstance(provider, TracerProvider) else None

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": settings.app_version,
            "deployment.environment": settings.environment,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.otel_exporter_otlp_endpoint is not None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    _instrument_redis()
    _instrument_kafka()
    _initialized = True

    logger.info(
        "tracing_configured",
        service_name=service_name,
        otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    )
    return provider


def instrument_sqlalchemy_engine(engine: Engine, *, settings: Settings) -> None:
    """Attach SQLAlchemy auto-instrumentation to a database engine."""
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        enable_commenter=True,
        commenter_options={"db_driver": True},
    )


def instrument_fastapi_app(app: FastAPI, *, settings: Settings) -> None:
    """Attach FastAPI auto-instrumentation to the application."""
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)


def shutdown_tracing() -> None:
    """Flush and shut down the tracer provider when tracing is active."""
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.shutdown()


def _instrument_redis() -> None:
    global _redis_instrumented
    if _redis_instrumented:
        return

    from opentelemetry.instrumentation.redis import RedisInstrumentor

    RedisInstrumentor().instrument()
    _redis_instrumented = True


def _instrument_kafka() -> None:
    global _kafka_instrumented
    if _kafka_instrumented:
        return

    try:
        import kafka  # noqa: F401
    except ImportError:
        logger.debug("kafka_python_not_installed_skipping_kafka_tracing")
        return

    from opentelemetry.instrumentation.kafka import KafkaInstrumentor

    KafkaInstrumentor().instrument()
    _kafka_instrumented = True

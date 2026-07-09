"""Tests for OpenTelemetry tracing configuration and manual spans."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.tracing.config import configure_tracing
from backend.app.infrastructure.tracing.spans import business_span


def test_configure_tracing_disabled_returns_none() -> None:
    settings = Settings(otel_enabled=False)

    provider = configure_tracing(settings, service_name="odis-test")

    assert provider is None


def test_business_span_records_operation_name_and_attributes() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    with business_span(
        "enqueue_reasoning_job",
        attributes={"asset_id": "asset-123"},
    ):
        pass

    finished = exporter.get_finished_spans()
    assert len(finished) == 1
    assert finished[0].name == "enqueue_reasoning_job"
    assert finished[0].attributes is not None
    assert finished[0].attributes["asset_id"] == "asset-123"

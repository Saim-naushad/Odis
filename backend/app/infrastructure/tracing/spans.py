"""Manual span helpers for important business operations."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Span

TRACER_NAME = "odis.backend"


def get_tracer() -> trace.Tracer:
    """Return the shared backend tracer."""
    return trace.get_tracer(TRACER_NAME)


@contextmanager
def business_span(
    name: str,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[Span]:
    """Create a manual span for an important business operation."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes is not None:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)
        yield span

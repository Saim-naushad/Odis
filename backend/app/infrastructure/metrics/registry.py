"""Central Prometheus metric registry and exposition helpers."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

# Import metric modules so collectors register with REGISTRY at startup.
from backend.app.infrastructure.metrics import (  # noqa: F401
    http_metrics,
    monitoring_metrics,
    observation_metrics,
    reasoning_metrics,
)

__all__ = ["CONTENT_TYPE_LATEST", "REGISTRY", "generate_metrics"]


def generate_metrics() -> bytes:
    """Return all registered metrics in Prometheus text exposition format."""
    return generate_latest(REGISTRY)

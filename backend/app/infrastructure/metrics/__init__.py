"""Prometheus metrics for the ODIS platform API."""

from backend.app.infrastructure.metrics.registry import (
    CONTENT_TYPE_LATEST,
    generate_metrics,
)

__all__ = ["CONTENT_TYPE_LATEST", "generate_metrics"]

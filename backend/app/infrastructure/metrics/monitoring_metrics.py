"""Monitoring stream metrics."""

from __future__ import annotations

from prometheus_client import Gauge

monitoring_sse_connections = Gauge(
    "monitoring_sse_connections",
    "Number of active monitoring SSE connections",
)

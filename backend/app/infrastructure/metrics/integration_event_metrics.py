"""Integration event publishing metrics."""

from __future__ import annotations

from prometheus_client import Counter

integration_events_published_total = Counter(
    "integration_events_published_total",
    "Total number of integration events published to external transport",
)

integration_publish_failures_total = Counter(
    "integration_publish_failures_total",
    "Total number of integration event publish failures",
)


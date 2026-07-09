"""Recommendation computation metrics."""

from __future__ import annotations

from prometheus_client import Counter

recommendations_computed_total = Counter(
    "recommendations_computed_total",
    "Total number of recommendations computed during reasoning",
    labelnames=("category", "priority", "urgency"),
)


def record_recommendation_computed(
    *,
    category: str,
    priority: str,
    urgency: str,
) -> None:
    """Increment when a recommendation is produced from operational state."""
    recommendations_computed_total.labels(
        category=category,
        priority=priority,
        urgency=urgency,
    ).inc()

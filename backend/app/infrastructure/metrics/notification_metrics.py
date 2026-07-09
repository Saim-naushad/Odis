"""Notification lifecycle metrics."""

from __future__ import annotations

from prometheus_client import Counter

notifications_created_total = Counter(
    "notifications_created_total",
    "Total number of notifications created during reasoning",
    labelnames=("severity", "status"),
)


def record_notification_created(
    *,
    severity: str,
    status: str,
) -> None:
    """Increment when a new notification is emitted."""
    notifications_created_total.labels(
        severity=severity,
        status=status,
    ).inc()

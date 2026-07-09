"""Integration event publishing metrics."""

from __future__ import annotations

from prometheus_client import Counter

integration_events_digital_twin_updated_total = Counter(
    "integration_events_digital_twin_updated_total",
    "Total DigitalTwinUpdated integration events published",
)

integration_events_operational_state_changed_total = Counter(
    "integration_events_operational_state_changed_total",
    "Total OperationalStateChanged integration events published",
)

integration_events_notification_raised_total = Counter(
    "integration_events_notification_raised_total",
    "Total NotificationRaised integration events published",
)

integration_publish_failures_total = Counter(
    "integration_publish_failures_total",
    "Total number of integration event publish failures",
)

_INTEGRATION_EVENT_COUNTERS: dict[str, Counter] = {
    "DigitalTwinUpdated": integration_events_digital_twin_updated_total,
    "OperationalStateChanged": integration_events_operational_state_changed_total,
    "NotificationRaised": integration_events_notification_raised_total,
}


def record_integration_event_published(event_type: str) -> None:
    """Increment the counter for the published integration event type."""
    counter = _INTEGRATION_EVENT_COUNTERS.get(event_type)
    if counter is not None:
        counter.inc()


def record_integration_publish_failure() -> None:
    """Increment when publishing an integration event fails."""
    integration_publish_failures_total.inc()

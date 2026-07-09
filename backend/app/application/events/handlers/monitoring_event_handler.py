"""Handlers that translate domain events into monitoring SSE events."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.application.events.domain_events import (
    ObservationCreated,
    ReasoningCompleted,
)
from backend.app.application.monitoring_event_source import (
    MonitoringEvent,
    MonitoringEventSource,
)


class MonitoringEventHandler:
    """Publish monitoring updates in response to domain events."""

    def __init__(self, event_source: MonitoringEventSource) -> None:
        self._event_source = event_source

    def on_observation_created(self, event: ObservationCreated) -> None:
        self._event_source.publish(
            MonitoringEvent.create(
                event_type="asset_updated",
                asset_id=event.asset_id,
                timestamp=_to_iso(event.timestamp),
            )
        )

    def on_reasoning_completed(self, event: ReasoningCompleted) -> None:
        self._event_source.publish(
            MonitoringEvent.create(
                event_type="run_updated",
                asset_id=event.asset_id,
                run_id=event.run_id,
                timestamp=_to_iso(event.timestamp),
            )
        )
        self._event_source.publish(
            MonitoringEvent.create(
                event_type="asset_updated",
                asset_id=event.asset_id,
                run_id=event.run_id,
                timestamp=_to_iso(event.timestamp),
            )
        )


def _to_iso(timestamp: datetime) -> str:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.isoformat()


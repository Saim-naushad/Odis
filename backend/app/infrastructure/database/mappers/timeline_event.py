"""Mapping between domain timeline events and ORM models."""

from datetime import UTC, datetime
from typing import cast

from backend.app.domain.timeline import TimelineEvent, TimelineEventType
from backend.app.infrastructure.database.models.timeline_event import TimelineEventModel


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def timeline_event_to_model(event: TimelineEvent) -> TimelineEventModel:
    """Map a domain timeline event to its SQLAlchemy representation."""
    return TimelineEventModel(
        id=event.id,
        asset_id=event.asset_id,
        timestamp=event.timestamp,
        event_type=event.event_type,
        title=event.title,
        description=event.description,
        metadata_json=event.metadata,
    )


def timeline_event_to_domain(model: TimelineEventModel) -> TimelineEvent:
    """Map a SQLAlchemy timeline event row to the domain entity."""
    return TimelineEvent(
        id=model.id,
        asset_id=model.asset_id,
        timestamp=_ensure_utc(model.timestamp),
        event_type=cast(TimelineEventType, model.event_type),
        title=model.title,
        description=model.description,
        metadata=model.metadata_json,
    )

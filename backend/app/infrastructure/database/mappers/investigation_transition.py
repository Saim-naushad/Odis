"""Mapping between domain investigation transitions and ORM models."""

from datetime import UTC, datetime
from typing import cast

from backend.app.domain.investigation import InvestigationEvent, InvestigationStatus
from backend.app.infrastructure.database.models.investigation_transition import (
    InvestigationTransitionModel,
)


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def investigation_transition_to_model(
    event: InvestigationEvent,
) -> InvestigationTransitionModel:
    """Map a domain investigation transition to its SQLAlchemy representation."""
    return InvestigationTransitionModel(
        id=event.id,
        asset_id=event.asset_id,
        recommendation_id=event.recommendation_id,
        status=event.status,
        actor_id=event.actor_id,
        actor_display_name=event.actor_display_name,
        occurred_at=event.occurred_at,
        notes=event.notes,
    )


def investigation_transition_to_domain(
    model: InvestigationTransitionModel,
) -> InvestigationEvent:
    """Map a SQLAlchemy investigation transition row to the domain entity."""
    return InvestigationEvent(
        id=model.id,
        asset_id=model.asset_id,
        recommendation_id=model.recommendation_id,
        status=cast(InvestigationStatus, model.status),
        actor_id=model.actor_id,
        actor_display_name=model.actor_display_name,
        occurred_at=_ensure_utc(model.occurred_at),
        notes=model.notes,
    )

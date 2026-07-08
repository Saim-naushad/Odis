"""Mapping between domain decision contexts and ORM models."""

from datetime import UTC, datetime

from backend.app.infrastructure.database.models.decision_context import (
    DecisionContextModel,
)
from domain.entities.decision_context import DecisionContext


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def decision_context_to_model(context: DecisionContext) -> DecisionContextModel:
    """Map a domain decision context to its SQLAlchemy representation."""
    return DecisionContextModel(
        id=context.id,
        goal_id=context.goal_id,
        situation_id=context.situation_id,
        assessment=context.assessment,
        created_at=context.created_at,
    )


def decision_context_to_domain(model: DecisionContextModel) -> DecisionContext:
    """Map a SQLAlchemy decision context row to the domain entity."""
    return DecisionContext(
        id=model.id,
        goal_id=model.goal_id,
        situation_id=model.situation_id,
        assessment=model.assessment,
        created_at=_ensure_utc(model.created_at),
    )

"""Mapping between domain decision plans and ORM models."""

from datetime import UTC, datetime

from backend.app.infrastructure.database.models.decision_plan import DecisionPlanModel
from domain.entities.decision_plan import DecisionPlan
from domain.value_objects.priority import Priority


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def decision_plan_to_model(plan: DecisionPlan) -> DecisionPlanModel:
    """Map a domain decision plan to its SQLAlchemy representation."""
    return DecisionPlanModel(
        id=plan.id,
        context_id=plan.context_id,
        created_at=plan.created_at,
        priority=plan.priority.value,
        recommendation=plan.recommendation,
        justification=plan.justification,
    )


def decision_plan_to_domain(model: DecisionPlanModel) -> DecisionPlan:
    """Map a SQLAlchemy decision plan row to the domain entity."""
    return DecisionPlan(
        id=model.id,
        context_id=model.context_id,
        created_at=_ensure_utc(model.created_at),
        priority=Priority(model.priority),
        recommendation=model.recommendation,
        justification=model.justification,
    )

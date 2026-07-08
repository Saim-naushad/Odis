"""Mapping between domain reasoning runs and ORM models."""

from datetime import UTC, datetime

from application.reasoning_run import ReasoningRun
from backend.app.infrastructure.database.models.reasoning_run import ReasoningRunModel
from domain.repositories.reasoning_run_repository import PersistedReasoningRun


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def reasoning_run_to_model(run: PersistedReasoningRun) -> ReasoningRunModel:
    """Map an application reasoning run to its SQLAlchemy representation."""
    return ReasoningRunModel(
        id=run.id,
        started_at=run.started_at,
    )


def reasoning_run_to_domain(model: ReasoningRunModel) -> ReasoningRun:
    """Map a SQLAlchemy reasoning run row to the application model."""
    return ReasoningRun(
        id=model.id,
        started_at=_ensure_utc(model.started_at),
    )

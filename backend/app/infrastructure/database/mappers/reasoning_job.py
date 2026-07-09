"""Mapping between domain reasoning jobs and ORM models."""

from datetime import UTC, datetime

from backend.app.domain.reasoning_job import ReasoningJob, ReasoningJobStatus
from backend.app.infrastructure.database.models.reasoning_job import ReasoningJobModel


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def reasoning_job_to_model(job: ReasoningJob) -> ReasoningJobModel:
    """Map a domain reasoning job to its SQLAlchemy representation."""
    return ReasoningJobModel(
        id=job.id,
        asset_id=job.asset_id,
        status=job.status.value,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        attempts=job.attempts,
    )


def reasoning_job_to_domain(model: ReasoningJobModel) -> ReasoningJob:
    """Map a SQLAlchemy reasoning job row to the domain entity."""
    return ReasoningJob(
        id=model.id,
        asset_id=model.asset_id,
        status=ReasoningJobStatus(model.status),
        created_at=_ensure_utc(model.created_at),
        started_at=_ensure_utc(model.started_at) if model.started_at else None,
        completed_at=_ensure_utc(model.completed_at) if model.completed_at else None,
        attempts=model.attempts,
    )

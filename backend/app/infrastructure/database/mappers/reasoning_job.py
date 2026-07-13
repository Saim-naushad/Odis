"""Mapping between domain reasoning jobs and ORM models."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.engine import Row

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
        dirty=job.dirty,
        coalesced_count=job.coalesced_count,
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
        dirty=model.dirty,
        coalesced_count=model.coalesced_count,
    )


def reasoning_job_row_to_domain(row: Row[Any]) -> ReasoningJob:
    """Map a raw ``RETURNING`` row (matching ``ReasoningJobModel`` column
    order) to the domain entity.

    Used by atomic upsert/update statements executed directly via
    ``session.execute`` instead of through the ORM identity map, so the
    returned values always reflect the just-committed row rather than a
    potentially stale already-loaded instance.
    """
    return ReasoningJob(
        id=row.id,
        asset_id=row.asset_id,
        status=ReasoningJobStatus(row.status),
        created_at=_ensure_utc(row.created_at),
        started_at=_ensure_utc(row.started_at) if row.started_at else None,
        completed_at=_ensure_utc(row.completed_at) if row.completed_at else None,
        attempts=row.attempts,
        dirty=bool(row.dirty),
        coalesced_count=row.coalesced_count,
    )

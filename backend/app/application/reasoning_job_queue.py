"""Abstraction for durable reasoning job queues.

The database-backed implementation is the default. A future Kafka-backed
queue can implement the same protocol without changing the reasoning engine
or worker orchestration logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from backend.app.domain.reasoning_job import ReasoningJob, ReasoningJobStatus
from backend.app.domain.repositories.reasoning_job_repository import (
    ReasoningJobRepository,
)


class ReasoningJobQueue(Protocol):
    """Enqueue and claim reasoning jobs from a durable queue."""

    def enqueue(self, asset_id: str) -> ReasoningJob:
        """Add a pending reasoning job for the given asset."""

    def claim(self) -> ReasoningJob | None:
        """Claim the oldest pending job, marking it RUNNING."""

    def complete(self, job: ReasoningJob) -> ReasoningJob:
        """Mark a claimed job as completed."""

    def fail(self, job: ReasoningJob) -> ReasoningJob:
        """Mark a claimed job as failed."""


class DatabaseReasoningJobQueue:
    """PostgreSQL-backed reasoning job queue."""

    def __init__(self, repository: ReasoningJobRepository) -> None:
        self._repository = repository

    def enqueue(self, asset_id: str) -> ReasoningJob:
        job = ReasoningJob(
            id=str(uuid4()),
            asset_id=asset_id,
            status=ReasoningJobStatus.PENDING,
            created_at=datetime.now(UTC),
            started_at=None,
            completed_at=None,
            attempts=0,
        )
        self._repository.save(job)
        return job

    def claim(self) -> ReasoningJob | None:
        return self._repository.claim_oldest_pending()

    def complete(self, job: ReasoningJob) -> ReasoningJob:
        completed = ReasoningJob(
            id=job.id,
            asset_id=job.asset_id,
            status=ReasoningJobStatus.COMPLETED,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=datetime.now(UTC),
            attempts=job.attempts,
        )
        self._repository.update(completed)
        return completed

    def fail(self, job: ReasoningJob) -> ReasoningJob:
        failed = ReasoningJob(
            id=job.id,
            asset_id=job.asset_id,
            status=ReasoningJobStatus.FAILED,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=datetime.now(UTC),
            attempts=job.attempts,
        )
        self._repository.update(failed)
        return failed

"""Abstraction for durable reasoning job queues.

The database-backed implementation is the default. A future Kafka-backed
queue can implement the same protocol without changing the reasoning engine
or worker orchestration logic.
"""

from __future__ import annotations

from typing import Protocol

from backend.app.domain.reasoning_job import ReasoningJob
from backend.app.domain.repositories.reasoning_job_repository import (
    ReasoningJobRepository,
)
from backend.app.infrastructure.metrics.worker_metrics import (
    record_reasoning_job_coalesced,
    record_reasoning_job_completed,
    record_reasoning_job_created,
    record_reasoning_job_failed,
    record_reasoning_job_rescheduled,
    record_reasoning_job_running_finished,
    record_reasoning_job_running_started,
)
from backend.app.infrastructure.tracing import business_span


class ReasoningJobQueue(Protocol):
    """Enqueue and claim reasoning jobs from a durable queue."""

    def enqueue(self, asset_id: str) -> ReasoningJob:
        """Signal that the given asset needs reasoning.

        Returns the asset's current outstanding job — a new one if none was
        outstanding, or the existing one if this request was absorbed into
        it (marked dirty) instead of creating a duplicate.
        """

    def claim(self) -> ReasoningJob | None:
        """Claim the oldest pending job, marking it RUNNING."""

    def complete(self, job: ReasoningJob) -> ReasoningJob:
        """Mark a claimed job as completed, rescheduling if it went dirty."""

    def fail(self, job: ReasoningJob) -> ReasoningJob:
        """Mark a claimed job as failed, rescheduling if it went dirty."""


class DatabaseReasoningJobQueue:
    """PostgreSQL-backed reasoning job queue."""

    def __init__(self, repository: ReasoningJobRepository) -> None:
        self._repository = repository

    def enqueue(self, asset_id: str) -> ReasoningJob:
        with business_span("enqueue_reasoning_job", attributes={"asset_id": asset_id}):
            job, created = self._repository.enqueue_or_mark_dirty(asset_id)
            if created:
                record_reasoning_job_created()
            else:
                record_reasoning_job_coalesced()
            return job

    def claim(self) -> ReasoningJob | None:
        job = self._repository.claim_oldest_pending()
        if job is not None:
            record_reasoning_job_running_started()
        return job

    def complete(self, job: ReasoningJob) -> ReasoningJob:
        completed, rescheduled = self._repository.complete_and_reschedule(job)
        record_reasoning_job_running_finished()
        record_reasoning_job_completed()
        if rescheduled is not None:
            record_reasoning_job_created()
            record_reasoning_job_rescheduled()
        return completed

    def fail(self, job: ReasoningJob) -> ReasoningJob:
        failed, rescheduled = self._repository.fail_and_reschedule(job)
        record_reasoning_job_running_finished()
        record_reasoning_job_failed()
        if rescheduled is not None:
            record_reasoning_job_created()
            record_reasoning_job_rescheduled()
        return failed

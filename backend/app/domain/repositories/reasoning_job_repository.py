"""Repository contract for reasoning job persistence."""

from __future__ import annotations

from typing import Protocol

from backend.app.domain.reasoning_job import ReasoningJob


class ReasoningJobRepository(Protocol):
    """Persist and claim reasoning jobs from a durable queue."""

    def save(self, job: ReasoningJob) -> None:
        """Persist a new reasoning job."""

    def get(self, job_id: str) -> ReasoningJob | None:
        """Return a reasoning job when it exists."""

    def claim_oldest_pending(self) -> ReasoningJob | None:
        """Atomically claim the oldest pending job and mark it RUNNING."""

    def update(self, job: ReasoningJob) -> None:
        """Persist changes to an existing reasoning job."""

    def count_by_status(self, status: str) -> int:
        """Return how many jobs are in the given status."""

    def enqueue_or_mark_dirty(self, asset_id: str) -> tuple[ReasoningJob, bool]:
        """Create the asset's outstanding job, or mark it dirty if one exists.

        At most one PENDING/RUNNING job per asset ever exists. Returns
        ``(job, created)``: ``created`` is True when a new row was inserted,
        False when an already-outstanding job absorbed this request instead.
        """

    def complete_and_reschedule(
        self, job: ReasoningJob
    ) -> tuple[ReasoningJob, ReasoningJob | None]:
        """Mark ``job`` COMPLETED and, if it was dirty, atomically schedule
        exactly one follow-up PENDING job for the same asset.

        Returns ``(completed_job, rescheduled_job_or_none)``.
        """

    def fail_and_reschedule(
        self, job: ReasoningJob
    ) -> tuple[ReasoningJob, ReasoningJob | None]:
        """Mark ``job`` FAILED and, if it was dirty, atomically schedule
        exactly one follow-up PENDING job for the same asset.

        Returns ``(failed_job, rescheduled_job_or_none)``.
        """

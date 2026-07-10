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

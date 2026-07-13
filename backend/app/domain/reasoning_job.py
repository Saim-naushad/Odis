"""Domain entity for asynchronous reasoning job orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ReasoningJobStatus(StrEnum):
    """Lifecycle states for a reasoning job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ReasoningJob:
    """A durable unit of work that triggers reasoning for an asset.

    At most one job per asset may be PENDING or RUNNING at a time (enforced
    by a partial unique index on the underlying table). ``dirty`` records
    that an observation arrived while this job was already outstanding, so
    exactly one follow-up job must be scheduled when this one completes or
    fails. ``coalesced_count`` counts how many enqueue requests were absorbed
    by this job instead of creating a new row.
    """

    id: str
    asset_id: str
    status: ReasoningJobStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    attempts: int
    dirty: bool = False
    coalesced_count: int = 0

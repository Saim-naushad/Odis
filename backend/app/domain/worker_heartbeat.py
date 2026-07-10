"""Domain model for reasoning worker liveness tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WorkerHeartbeat:
    """A single worker's most recent heartbeat timestamp."""

    worker_id: str
    last_seen_at: datetime

"""Repository contract for worker heartbeat persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from backend.app.domain.worker_heartbeat import WorkerHeartbeat


class WorkerHeartbeatRepository(Protocol):
    """Persist and read worker heartbeat records."""

    def upsert(self, worker_id: str, last_seen_at: datetime) -> None:
        """Insert or update the heartbeat for a worker."""

    def get_most_recent(self) -> WorkerHeartbeat | None:
        """Return the freshest heartbeat across all workers, if any."""

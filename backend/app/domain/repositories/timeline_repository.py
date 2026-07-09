"""Repository contract for asset investigation timeline events."""

from __future__ import annotations

from typing import Protocol

from backend.app.domain.timeline import TimelineEvent


class TimelineRepository(Protocol):
    """Persist and query operational timeline events by asset."""

    def save(self, event: TimelineEvent) -> None:
        """Persist a new timeline event."""

    def list_by_asset(self, asset_id: str) -> list[TimelineEvent]:
        """Return timeline events for an asset in chronological order."""

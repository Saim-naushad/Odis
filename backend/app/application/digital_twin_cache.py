"""Cache abstraction for assembled Digital Twins."""

from __future__ import annotations

from typing import Protocol

from backend.app.domain.digital_twin import DigitalTwin


class DigitalTwinCache(Protocol):
    """Store and retrieve assembled Digital Twins by asset identifier."""

    def get(self, asset_id: str) -> DigitalTwin | None:
        """Return a cached Digital Twin when present."""

    def set(self, digital_twin: DigitalTwin) -> None:
        """Store an assembled Digital Twin."""

    def invalidate(self, asset_id: str) -> None:
        """Remove a cached Digital Twin for the given asset."""

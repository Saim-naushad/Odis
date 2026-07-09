"""In-memory Digital Twin cache (default implementation)."""

from __future__ import annotations

from backend.app.domain.digital_twin import DigitalTwin


class MemoryDigitalTwinCache:
    """Process-local cache backed by a dictionary."""

    def __init__(self) -> None:
        self._store: dict[str, DigitalTwin] = {}

    def get(self, asset_id: str) -> DigitalTwin | None:
        return self._store.get(asset_id)

    def set(self, digital_twin: DigitalTwin) -> None:
        self._store[digital_twin.asset_id] = digital_twin

    def invalidate(self, asset_id: str) -> None:
        self._store.pop(asset_id, None)

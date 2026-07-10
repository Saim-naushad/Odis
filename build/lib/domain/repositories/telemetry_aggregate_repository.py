"""Repository contract for downsampled telemetry aggregates."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from domain.value_objects.telemetry_aggregate import TelemetryAggregatePoint
from domain.value_objects.telemetry_bucket import TelemetryBucket


class TelemetryAggregateRepository(ABC):
    """Read pre-computed telemetry rollups for an asset."""

    @abstractmethod
    def list_by_asset(
        self,
        asset_id: str,
        *,
        bucket: TelemetryBucket,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: str | None = None,
    ) -> list[TelemetryAggregatePoint]:
        """Return aggregate points ordered oldest bucket first."""
        pass

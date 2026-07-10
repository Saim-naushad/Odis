"""Immutable telemetry history projections for operator-facing APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TelemetrySample:
    """A single timestamped measurement value within a telemetry series."""

    timestamp: datetime
    value: float


@dataclass(frozen=True)
class TelemetrySeries:
    """Ordered historical measurements for one asset and measurement type.

    Immutable read model assembled by ``TelemetryHistoryService``. Samples are
    stored oldest-first so operators and future chart components can render
    chronologically without re-sorting.
    """

    asset_id: str
    measurement_type: str
    unit: str
    samples: tuple[TelemetrySample, ...]

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not self.measurement_type:
            raise ValueError("measurement_type must not be empty")
        if not self.unit:
            raise ValueError("unit must not be empty")
        for index in range(1, len(self.samples)):
            previous = self.samples[index - 1]
            current = self.samples[index]
            if current.timestamp < previous.timestamp:
                raise ValueError("samples must be ordered oldest to newest")

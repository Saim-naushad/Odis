"""Immutable telemetry aggregate projections for downsampled history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TelemetryAggregatePoint:
    """One pre-aggregated bucket for an asset measurement type."""

    bucket: datetime
    measurement_type: str
    avg_value: float
    min_value: float
    max_value: float
    sample_count: int
    unit: str

    def __post_init__(self) -> None:
        if not self.measurement_type:
            raise ValueError("measurement_type must not be empty")
        if not self.unit:
            raise ValueError("unit must not be empty")
        if self.sample_count < 1:
            raise ValueError("sample_count must be at least 1")

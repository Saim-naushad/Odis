"""Immutable telemetry forecast projections for operator-facing APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ForecastSample:
    """A single predicted measurement value on a future horizon point."""

    timestamp: datetime
    value: float


@dataclass(frozen=True)
class TelemetryForecast:
    """Ordered future measurements for one asset and measurement type.

    Immutable read model assembled by ``ForecastInferenceService``. Samples are
    stored oldest-first so operators and chart components can overlay forecasts
    on historical telemetry without re-sorting.
    """

    asset_id: str
    measurement_type: str
    unit: str
    model_id: str
    horizon_start: datetime
    generated_at: datetime
    samples: tuple[ForecastSample, ...]

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not self.measurement_type:
            raise ValueError("measurement_type must not be empty")
        if not self.unit:
            raise ValueError("unit must not be empty")
        if not self.model_id:
            raise ValueError("model_id must not be empty")
        for sample in self.samples:
            if sample.timestamp <= self.horizon_start:
                raise ValueError("forecast samples must be after horizon_start")
        for index in range(1, len(self.samples)):
            previous = self.samples[index - 1]
            current = self.samples[index]
            if current.timestamp < previous.timestamp:
                raise ValueError("samples must be ordered oldest to newest")

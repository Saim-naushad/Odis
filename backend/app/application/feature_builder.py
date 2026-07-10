"""Convert telemetry read models into model-ready feature tensors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from domain.value_objects.telemetry_aggregate import TelemetryAggregatePoint
from domain.value_objects.telemetry_series import TelemetrySeries

MIN_FEATURE_STD = 1e-6


@dataclass(frozen=True, slots=True)
class ModelFeatures:
    """Normalized feature window ready for ONNX inference."""

    values: tuple[float, ...]
    mean: float
    std: float

    def denormalize(self, normalized_values: Sequence[float]) -> tuple[float, ...]:
        """Map model outputs back to measurement units."""
        return tuple(
            (value * self.std) + self.mean for value in normalized_values
        )


@dataclass(frozen=True, slots=True)
class FeatureBuilder:
    """Build fixed-length normalized tensors from telemetry projections."""

    context_length: int

    def build_from_series(self, series: TelemetrySeries) -> ModelFeatures:
        """Extract a feature window from raw chronological telemetry."""
        values = [sample.value for sample in series.samples]
        return self._build(values)

    def build_from_aggregate_points(
        self,
        points: Sequence[TelemetryAggregatePoint],
    ) -> ModelFeatures:
        """Extract a feature window from downsampled aggregate buckets."""
        ordered = sorted(points, key=lambda point: point.bucket)
        values = [point.avg_value for point in ordered]
        return self._build(values)

    def _build(self, values: list[float]) -> ModelFeatures:
        if not values:
            msg = "at least one telemetry value is required to build features"
            raise ValueError(msg)

        window = values[-self.context_length :]
        if len(window) < self.context_length:
            pad_value = window[0]
            padding = [pad_value] * (self.context_length - len(window))
            window = padding + window

        mean = sum(window) / len(window)
        variance = sum((value - mean) ** 2 for value in window) / len(window)
        std = variance**0.5
        if std < MIN_FEATURE_STD:
            std = MIN_FEATURE_STD

        normalized = tuple((value - mean) / std for value in window)
        return ModelFeatures(values=normalized, mean=mean, std=std)

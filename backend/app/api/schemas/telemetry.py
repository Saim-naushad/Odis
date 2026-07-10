"""Telemetry history API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from domain.value_objects.telemetry_aggregate import TelemetryAggregatePoint
from domain.value_objects.telemetry_bucket import TelemetryBucket
from domain.value_objects.telemetry_series import TelemetrySample, TelemetrySeries


class TelemetrySampleResponse(BaseModel):
    """A single timestamped measurement value."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "timestamp": "2026-01-01T12:00:00Z",
                "value": 42.5,
            }
        }
    )

    timestamp: datetime
    value: float

    @classmethod
    def from_domain(cls, sample: TelemetrySample) -> Self:
        return cls(timestamp=sample.timestamp, value=sample.value)


class TelemetrySeriesResponse(BaseModel):
    """Historical measurements for one asset metric."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "asset_id": "asset-stack-1",
                "measurement_type": "stack_temperature",
                "unit": "celsius",
                "samples": [
                    {
                        "timestamp": "2026-01-01T12:00:00Z",
                        "value": 42.5,
                    }
                ],
            }
        }
    )

    asset_id: str
    measurement_type: str
    unit: str
    samples: list[TelemetrySampleResponse] = Field(
        description="Chronological samples, oldest first",
    )

    @classmethod
    def from_domain(cls, series: TelemetrySeries) -> Self:
        return cls(
            asset_id=series.asset_id,
            measurement_type=series.measurement_type,
            unit=series.unit,
            samples=[
                TelemetrySampleResponse.from_domain(sample)
                for sample in series.samples
            ],
        )


class TelemetryAggregateSampleResponse(BaseModel):
    """One downsampled bucket with aggregate statistics."""

    timestamp: datetime
    avg_value: float
    min_value: float
    max_value: float
    sample_count: int


class TelemetryAggregateSeriesResponse(BaseModel):
    """Downsampled telemetry for one asset metric."""

    asset_id: str
    measurement_type: str
    unit: str
    bucket: str = Field(description="Aggregate bucket width (1h or 1d)")
    samples: list[TelemetryAggregateSampleResponse] = Field(
        description="Chronological aggregate buckets, oldest first",
    )

    @classmethod
    def from_points(
        cls,
        *,
        asset_id: str,
        bucket: TelemetryBucket,
        measurement_type: str,
        unit: str,
        points: list[TelemetryAggregatePoint],
    ) -> Self:
        return cls(
            asset_id=asset_id,
            measurement_type=measurement_type,
            unit=unit,
            bucket=bucket.value,
            samples=[
                TelemetryAggregateSampleResponse(
                    timestamp=point.bucket,
                    avg_value=point.avg_value,
                    min_value=point.min_value,
                    max_value=point.max_value,
                    sample_count=point.sample_count,
                )
                for point in points
            ],
        )

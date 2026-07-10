"""Application service for continuous-aggregate telemetry retrieval."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.telemetry_aggregate_repository import (
    TelemetryAggregateRepository,
)
from domain.value_objects.telemetry_aggregate import TelemetryAggregatePoint
from domain.value_objects.telemetry_bucket import TelemetryBucket
from domain.value_objects.telemetry_series import TelemetrySample, TelemetrySeries


class ContinuousAggregateService:
    """Retrieve downsampled telemetry from pre-computed rollups.

    Raw historical samples remain the responsibility of
    ``TelemetryHistoryService``. This service maps aggregate buckets into
    ``TelemetrySeries`` so operator APIs stay stable.
    """

    def __init__(
        self,
        *,
        observation_repository: ObservationRepository,
        telemetry_aggregate_repository: TelemetryAggregateRepository,
    ) -> None:
        self._observation_repository = observation_repository
        self._telemetry_aggregate_repository = telemetry_aggregate_repository

    def asset_exists(self, asset_id: str) -> bool:
        """Return whether any observations exist for the asset."""
        return bool(self._observation_repository.list_by_asset(asset_id))

    def get_aggregates(
        self,
        asset_id: str,
        *,
        bucket: TelemetryBucket,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: str | None = None,
    ) -> list[TelemetrySeries]:
        """Return aggregate telemetry grouped by measurement type."""
        points = self._telemetry_aggregate_repository.list_by_asset(
            asset_id,
            bucket=bucket,
            start=start,
            end=end,
            measurement_type=measurement_type,
        )
        return self._build_series(asset_id, points)

    def list_aggregate_points(
        self,
        asset_id: str,
        *,
        bucket: TelemetryBucket,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: str | None = None,
    ) -> list[TelemetryAggregatePoint]:
        """Return raw aggregate buckets for API enrichment."""
        return self._telemetry_aggregate_repository.list_by_asset(
            asset_id,
            bucket=bucket,
            start=start,
            end=end,
            measurement_type=measurement_type,
        )

    @staticmethod
    def resolve_bucket(
        bucket: TelemetryBucket | None,
        *,
        start: datetime | None,
        end: datetime | None,
    ) -> TelemetryBucket:
        """Choose aggregate granularity when the caller does not specify one."""
        if bucket is not None:
            return bucket

        if start is not None and end is not None:
            window = end - start
            if window.total_seconds() > 7 * 24 * 60 * 60:
                return TelemetryBucket.ONE_DAY

        return TelemetryBucket.ONE_HOUR

    def _build_series(
        self,
        asset_id: str,
        points: list[TelemetryAggregatePoint],
    ) -> list[TelemetrySeries]:
        grouped: dict[str, list[TelemetryAggregatePoint]] = defaultdict(list)
        for point in points:
            grouped[point.measurement_type].append(point)

        series: list[TelemetrySeries] = []
        for measurement_type in sorted(grouped):
            metric_points = grouped[measurement_type]
            metric_points.sort(key=lambda item: item.bucket)
            unit = metric_points[-1].unit
            samples = tuple(
                TelemetrySample(timestamp=item.bucket, value=item.avg_value)
                for item in metric_points
            )
            series.append(
                TelemetrySeries(
                    asset_id=asset_id,
                    measurement_type=measurement_type,
                    unit=unit,
                    samples=samples,
                )
            )
        return series

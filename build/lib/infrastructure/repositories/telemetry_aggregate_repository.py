"""In-memory telemetry aggregate repository for tests and local development."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from domain.entities.observation import Observation
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.telemetry_aggregate_repository import (
    TelemetryAggregateRepository,
)
from domain.value_objects.telemetry_aggregate import TelemetryAggregatePoint
from domain.value_objects.telemetry_bucket import TelemetryBucket

_BUCKET_WIDTH = {
    TelemetryBucket.ONE_HOUR: timedelta(hours=1),
    TelemetryBucket.ONE_DAY: timedelta(days=1),
}


def _bucket_start(timestamp: datetime, width: timedelta) -> datetime:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)

    if width == timedelta(days=1):
        return timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

    return timestamp.replace(minute=0, second=0, microsecond=0)


class InMemoryTelemetryAggregateRepository(TelemetryAggregateRepository):
    """Compute aggregate buckets from stored observations."""

    def __init__(self, *, observation_repository: ObservationRepository) -> None:
        self._observation_repository = observation_repository

    def list_by_asset(
        self,
        asset_id: str,
        *,
        bucket: TelemetryBucket,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: str | None = None,
    ) -> list[TelemetryAggregatePoint]:
        observations = self._observation_repository.list_by_asset_in_time_range(
            asset_id,
            start=start,
            end=end,
            measurement_type=measurement_type,
            newest_first=False,
        )
        return self._aggregate_observations(observations, bucket=bucket)

    @staticmethod
    def _aggregate_observations(
        observations: list[Observation],
        *,
        bucket: TelemetryBucket,
    ) -> list[TelemetryAggregatePoint]:
        width = _BUCKET_WIDTH[bucket]
        grouped: dict[tuple[datetime, str], list[Observation]] = defaultdict(list)

        for observation in observations:
            bucket_start = _bucket_start(observation.timestamp, width)
            key = (bucket_start, observation.measurement_type.name)
            grouped[key].append(observation)

        points: list[TelemetryAggregatePoint] = []
        for (bucket_start, measurement_type), bucket_observations in sorted(
            grouped.items()
        ):
            values = [item.value for item in bucket_observations]
            latest = max(
                bucket_observations,
                key=lambda item: (item.timestamp, item.id),
            )
            points.append(
                TelemetryAggregatePoint(
                    bucket=bucket_start,
                    measurement_type=measurement_type,
                    avg_value=sum(values) / len(values),
                    min_value=min(values),
                    max_value=max(values),
                    sample_count=len(values),
                    unit=latest.unit,
                )
            )

        return points

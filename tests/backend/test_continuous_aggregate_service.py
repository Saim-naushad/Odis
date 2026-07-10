"""Continuous aggregate service specifications."""

from datetime import UTC, datetime

import pytest

from backend.app.application.continuous_aggregate_service import (
    ContinuousAggregateService,
)
from domain.value_objects.telemetry_bucket import TelemetryBucket
from infrastructure.repositories.observation_repository import (
    InMemoryObservationRepository,
)
from infrastructure.repositories.telemetry_aggregate_repository import (
    InMemoryTelemetryAggregateRepository,
)
from tests.builders import build_measurement_type, build_observation


@pytest.fixture
def observation_repository() -> InMemoryObservationRepository:
    return InMemoryObservationRepository()


@pytest.fixture
def aggregate_repository(
    observation_repository: InMemoryObservationRepository,
) -> InMemoryTelemetryAggregateRepository:
    return InMemoryTelemetryAggregateRepository(
        observation_repository=observation_repository,
    )


@pytest.fixture
def service(
    observation_repository: InMemoryObservationRepository,
    aggregate_repository: InMemoryTelemetryAggregateRepository,
) -> ContinuousAggregateService:
    return ContinuousAggregateService(
        observation_repository=observation_repository,
        telemetry_aggregate_repository=aggregate_repository,
    )


def _save_observation(
    repository: InMemoryObservationRepository,
    *,
    observation_id: str,
    timestamp: str,
    value: float,
    measurement_type: str = "temperature",
    unit: str = "celsius",
) -> None:
    repository.save(
        build_observation(
            id=observation_id,
            asset_id="asset-1",
            timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
            measurement_type=build_measurement_type(name=measurement_type),
            value=value,
            unit=unit,
        )
    )


def test_get_aggregates_groups_hourly_buckets(
    observation_repository: InMemoryObservationRepository,
    service: ContinuousAggregateService,
) -> None:
    _save_observation(
        observation_repository,
        observation_id="obs-1",
        timestamp="2026-01-01T10:15:00Z",
        value=10.0,
    )
    _save_observation(
        observation_repository,
        observation_id="obs-2",
        timestamp="2026-01-01T10:45:00Z",
        value=14.0,
    )
    _save_observation(
        observation_repository,
        observation_id="obs-3",
        timestamp="2026-01-01T11:10:00Z",
        value=20.0,
    )

    series = service.get_aggregates("asset-1", bucket=TelemetryBucket.ONE_HOUR)

    assert len(series) == 1
    assert series[0].measurement_type == "temperature"
    assert [sample.value for sample in series[0].samples] == [12.0, 20.0]
    assert series[0].samples[0].timestamp == datetime(
        2026, 1, 1, 10, 0, tzinfo=UTC
    )


def test_get_aggregates_filters_by_measurement_type(
    observation_repository: InMemoryObservationRepository,
    service: ContinuousAggregateService,
) -> None:
    _save_observation(
        observation_repository,
        observation_id="obs-temp",
        timestamp="2026-01-01T10:00:00Z",
        value=10.0,
    )
    _save_observation(
        observation_repository,
        observation_id="obs-pressure",
        timestamp="2026-01-01T10:00:00Z",
        value=2.0,
        measurement_type="pressure",
        unit="bar",
    )

    series = service.get_aggregates(
        "asset-1",
        bucket=TelemetryBucket.ONE_HOUR,
        measurement_type="pressure",
    )

    assert len(series) == 1
    assert series[0].measurement_type == "pressure"
    assert series[0].unit == "bar"


def test_resolve_bucket_prefers_daily_for_long_windows() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 20, tzinfo=UTC)

    resolved = ContinuousAggregateService.resolve_bucket(
        None,
        start=start,
        end=end,
    )

    assert resolved is TelemetryBucket.ONE_DAY


def test_asset_exists(service: ContinuousAggregateService) -> None:
    assert service.asset_exists("asset-1") is False

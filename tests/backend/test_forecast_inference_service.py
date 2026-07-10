"""Forecast inference service specifications."""

from datetime import UTC, datetime, timedelta

import pytest

from backend.app.application.feature_builder import FeatureBuilder
from backend.app.application.forecast_inference_engine import ForecastModelSpec
from backend.app.application.forecast_inference_service import ForecastInferenceService
from domain.value_objects.telemetry_bucket import TelemetryBucket
from infrastructure.repositories.observation_repository import (
    InMemoryObservationRepository,
)
from infrastructure.repositories.telemetry_aggregate_repository import (
    InMemoryTelemetryAggregateRepository,
)
from tests.builders import build_measurement_type, build_observation


class _FakeForecastEngine:
    def __init__(self) -> None:
        self._spec = ForecastModelSpec(
            model_id="fake_v1",
            context_length=4,
            horizon_steps=2,
        )

    @property
    def model_spec(self) -> ForecastModelSpec:
        return self._spec

    def predict(self, features: tuple[float, ...]) -> tuple[float, ...]:
        last = features[-1]
        slope = features[-1] - features[-2]
        return (last + slope, last + (2 * slope))


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
) -> ForecastInferenceService:
    return ForecastInferenceService(
        observation_repository=observation_repository,
        telemetry_aggregate_repository=aggregate_repository,
        feature_builder=FeatureBuilder(context_length=4),
        inference_engine=_FakeForecastEngine(),
    )


def _save_hourly_observation(
    repository: InMemoryObservationRepository,
    *,
    observation_id: str,
    timestamp: datetime,
    value: float,
) -> None:
    repository.save(
        build_observation(
            id=observation_id,
            asset_id="asset-1",
            timestamp=timestamp,
            measurement_type=build_measurement_type(name="temperature"),
            value=value,
            unit="celsius",
        )
    )


def test_get_forecast_returns_domain_projection(
    observation_repository: InMemoryObservationRepository,
    service: ForecastInferenceService,
) -> None:
    base = datetime(2026, 1, 1, 8, 0, tzinfo=UTC)
    for index, value in enumerate((10.0, 12.0, 14.0, 16.0), start=1):
        _save_hourly_observation(
            observation_repository,
            observation_id=f"obs-{index}",
            timestamp=base + timedelta(hours=index - 1),
            value=value,
        )

    forecast = service.get_forecast(
        "asset-1",
        measurement_type="temperature",
        bucket=TelemetryBucket.ONE_HOUR,
    )

    assert forecast.asset_id == "asset-1"
    assert forecast.measurement_type == "temperature"
    assert forecast.model_id == "fake_v1"
    assert len(forecast.samples) == 2
    assert forecast.samples[0].timestamp > forecast.horizon_start


def test_get_forecast_raises_when_no_aggregate_history(
    observation_repository: InMemoryObservationRepository,
    service: ForecastInferenceService,
) -> None:
    _save_hourly_observation(
        observation_repository,
        observation_id="obs-1",
        timestamp=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        value=10.0,
    )

    with pytest.raises(ValueError, match="no aggregate telemetry"):
        service.get_forecast(
            "asset-1",
            measurement_type="missing-metric",
            bucket=TelemetryBucket.ONE_HOUR,
        )

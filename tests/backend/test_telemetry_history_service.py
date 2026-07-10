"""Telemetry history service specifications."""

from datetime import UTC, datetime

import pytest

from backend.app.application.telemetry_history_service import TelemetryHistoryService
from infrastructure.repositories.observation_repository import (
    InMemoryObservationRepository,
)
from tests.builders import build_measurement_type, build_observation


@pytest.fixture
def repository() -> InMemoryObservationRepository:
    return InMemoryObservationRepository()


@pytest.fixture
def service(repository: InMemoryObservationRepository) -> TelemetryHistoryService:
    return TelemetryHistoryService(observation_repository=repository)


def _save_series(
    repository: InMemoryObservationRepository,
    *,
    asset_id: str = "asset-1",
    measurement_type: str = "temperature",
    unit: str = "celsius",
    values: list[tuple[str, float]],
) -> None:
    for index, (timestamp, value) in enumerate(values):
        repository.save(
            build_observation(
                id=f"obs-{measurement_type}-{index}",
                asset_id=asset_id,
                timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
                measurement_type=build_measurement_type(name=measurement_type),
                value=value,
                unit=unit,
            )
        )


def test_get_history_groups_by_measurement_type(
    repository: InMemoryObservationRepository,
    service: TelemetryHistoryService,
) -> None:
    _save_series(
        repository,
        measurement_type="temperature",
        values=[("2026-01-01T10:00:00Z", 10.0), ("2026-01-01T10:01:00Z", 11.0)],
    )
    _save_series(
        repository,
        measurement_type="pressure",
        unit="bar",
        values=[("2026-01-01T10:00:00Z", 1.0)],
    )

    series = service.get_history("asset-1")

    assert len(series) == 2
    assert series[0].measurement_type == "pressure"
    assert series[1].measurement_type == "temperature"
    assert [sample.value for sample in series[1].samples] == [10.0, 11.0]


def test_get_history_filters_by_time_range(
    repository: InMemoryObservationRepository,
    service: TelemetryHistoryService,
) -> None:
    _save_series(
        repository,
        values=[
            ("2026-01-01T10:00:00Z", 10.0),
            ("2026-01-01T11:00:00Z", 11.0),
            ("2026-01-01T12:00:00Z", 12.0),
        ],
    )

    start = datetime(2026, 1, 1, 10, 30, tzinfo=UTC)
    end = datetime(2026, 1, 1, 11, 30, tzinfo=UTC)
    series = service.get_history("asset-1", start=start, end=end)

    assert len(series) == 1
    assert [sample.value for sample in series[0].samples] == [11.0]


def test_get_latest_returns_newest_per_measurement_type(
    repository: InMemoryObservationRepository,
    service: TelemetryHistoryService,
) -> None:
    _save_series(
        repository,
        measurement_type="temperature",
        values=[
            ("2026-01-01T10:00:00Z", 10.0),
            ("2026-01-01T11:00:00Z", 11.0),
        ],
    )
    _save_series(
        repository,
        measurement_type="pressure",
        unit="bar",
        values=[
            ("2026-01-01T09:00:00Z", 1.0),
            ("2026-01-01T12:00:00Z", 2.0),
        ],
    )

    series = service.get_latest("asset-1", limit=1)

    assert len(series) == 2
    by_type = {item.measurement_type: item for item in series}
    assert by_type["temperature"].samples[-1].value == 11.0
    assert by_type["pressure"].samples[-1].value == 2.0


def test_get_latest_with_measurement_filter(
    repository: InMemoryObservationRepository,
    service: TelemetryHistoryService,
) -> None:
    _save_series(
        repository,
        measurement_type="temperature",
        values=[
            ("2026-01-01T10:00:00Z", 10.0),
            ("2026-01-01T11:00:00Z", 11.0),
            ("2026-01-01T12:00:00Z", 12.0),
        ],
    )

    series = service.get_latest("asset-1", measurement_type="temperature", limit=2)

    assert len(series) == 1
    assert [sample.value for sample in series[0].samples] == [11.0, 12.0]


def test_asset_exists(service: TelemetryHistoryService) -> None:
    assert service.asset_exists("missing") is False

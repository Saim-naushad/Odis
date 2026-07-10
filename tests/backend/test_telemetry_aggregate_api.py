"""Telemetry aggregate API endpoint specifications."""

from collections.abc import Generator
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.main import create_app
from domain.repositories.observation_repository import ObservationRepository
from infrastructure.repositories.telemetry_aggregate_repository import (
    InMemoryTelemetryAggregateRepository,
)


@pytest.fixture
def sqlite_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "telemetry_aggregate_api.db"
    return Settings(database_url=f"sqlite:///{database_path}")


@pytest.fixture
def api_client(sqlite_settings: Settings) -> Generator[TestClient, None, None]:
    import backend.app.api.dependencies.repositories as repository_dependencies

    app = create_app(settings=sqlite_settings)

    def _override_aggregate_repository(
        observation_repository: Annotated[
            ObservationRepository,
            Depends(repository_dependencies.get_observation_repository),
        ],
    ) -> InMemoryTelemetryAggregateRepository:
        return InMemoryTelemetryAggregateRepository(
            observation_repository=observation_repository,
        )

    app.dependency_overrides[
        repository_dependencies.get_telemetry_aggregate_repository
    ] = _override_aggregate_repository

    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        yield client

    app.dependency_overrides.clear()


def _observation_payload(
    *,
    observation_id: str,
    asset_id: str = "asset-1",
    timestamp: str,
    measurement_type: str = "temperature",
    value: float,
    unit: str = "celsius",
) -> dict[str, object]:
    return {
        "id": observation_id,
        "asset_id": asset_id,
        "timestamp": timestamp,
        "measurement_type": measurement_type,
        "value": value,
        "unit": unit,
    }


def test_telemetry_aggregate_returns_hourly_buckets(api_client: TestClient) -> None:
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-1",
            timestamp="2026-01-01T10:15:00Z",
            value=10.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-2",
            timestamp="2026-01-01T10:45:00Z",
            value=14.0,
        ),
    )

    response = api_client.get(
        "/monitoring/assets/asset-1/telemetry/aggregate?bucket=1h"
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["bucket"] == "1h"
    assert body[0]["samples"][0]["avg_value"] == 12.0
    assert body[0]["samples"][0]["sample_count"] == 2


def test_telemetry_aggregate_requires_bucket(api_client: TestClient) -> None:
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-1",
            timestamp="2026-01-01T10:00:00Z",
            value=10.0,
        ),
    )

    response = api_client.get("/monitoring/assets/asset-1/telemetry/aggregate")

    assert response.status_code == 422


def test_telemetry_aggregate_returns_404_for_unknown_asset(
    api_client: TestClient,
) -> None:
    response = api_client.get(
        "/monitoring/assets/missing/telemetry/aggregate?bucket=1d"
    )

    assert response.status_code == 404

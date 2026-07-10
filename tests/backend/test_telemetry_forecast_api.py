"""Telemetry forecast API specifications."""

from collections.abc import Generator
from datetime import datetime
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
from tests.backend.helpers import drain_reasoning_jobs

pytest.importorskip("onnxruntime")


@pytest.fixture
def sqlite_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "forecast_api.db"
    return Settings(database_url=f"sqlite:///{database_path}", forecast_enabled=True)


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
    asset_id: str,
    timestamp: str,
    value: float,
    measurement_type: str = "stack_temperature",
) -> dict[str, object]:
    return {
        "id": observation_id,
        "asset_id": asset_id,
        "timestamp": timestamp,
        "measurement_type": measurement_type,
        "value": value,
        "unit": "celsius",
    }


def test_forecast_endpoint_returns_503_when_disabled(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'disabled.db'}",
        forecast_enabled=False,
    )
    app = create_app(settings=settings)
    with TestClient(app) as client:
        response = client.get("/monitoring/assets/asset-1/telemetry/forecast")
    assert response.status_code == 503


def test_forecast_endpoint_returns_forecasts_for_asset(
    api_client: TestClient,
) -> None:
    asset_id = "asset-forecast"
    for index in range(4):
        response = api_client.post(
            "/observations",
            json=_observation_payload(
                observation_id=f"obs-{index}",
                asset_id=asset_id,
                timestamp=f"2026-01-01T{10 + index:02d}:00:00Z",
                value=10.0 + index,
            ),
        )
        assert response.status_code == 202
    drain_reasoning_jobs(api_client)

    forecast_response = api_client.get(
        f"/monitoring/assets/{asset_id}/telemetry/forecast",
        params={"bucket": "1h", "measurement_type": "stack_temperature"},
    )
    assert forecast_response.status_code == 200
    payload = forecast_response.json()
    assert len(payload) == 1
    assert payload[0]["asset_id"] == asset_id
    assert payload[0]["model_id"] == "persistence_drift_v1"
    assert len(payload[0]["samples"]) == 12
    first_sample = datetime.fromisoformat(
        payload[0]["samples"][0]["timestamp"].replace("Z", "+00:00")
    )
    horizon_start = datetime.fromisoformat(
        payload[0]["horizon_start"].replace("Z", "+00:00")
    )
    assert first_sample > horizon_start

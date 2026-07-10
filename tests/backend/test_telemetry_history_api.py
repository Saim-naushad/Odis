"""Historical telemetry API endpoint specifications."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.main import create_app


@pytest.fixture
def sqlite_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "telemetry_history_api.db"
    return Settings(database_url=f"sqlite:///{database_path}")


@pytest.fixture
def api_client(sqlite_settings: Settings) -> Generator[TestClient, None, None]:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        yield client


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


def test_telemetry_history_returns_grouped_series(api_client: TestClient) -> None:
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-temp-1",
            timestamp="2026-01-01T10:00:00Z",
            value=10.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-temp-2",
            timestamp="2026-01-01T10:01:00Z",
            value=11.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-pressure-1",
            timestamp="2026-01-01T10:00:00Z",
            measurement_type="pressure",
            value=1.5,
            unit="bar",
        ),
    )

    response = api_client.get("/monitoring/assets/asset-1/telemetry")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    by_type = {item["measurement_type"]: item for item in body}
    assert by_type["pressure"]["unit"] == "bar"
    assert len(by_type["temperature"]["samples"]) == 2
    assert by_type["temperature"]["samples"][0]["value"] == 10.0
    assert by_type["temperature"]["samples"][1]["value"] == 11.0


def test_telemetry_history_filters_by_time_range(api_client: TestClient) -> None:
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-range-1",
            timestamp="2026-01-01T10:00:00Z",
            value=10.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-range-2",
            timestamp="2026-01-01T11:00:00Z",
            value=11.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-range-3",
            timestamp="2026-01-01T12:00:00Z",
            value=12.0,
        ),
    )

    response = api_client.get(
        "/monitoring/assets/asset-1/telemetry",
        params={
            "start": "2026-01-01T10:30:00Z",
            "end": "2026-01-01T11:30:00Z",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["samples"][0]["value"] == 11.0


def test_telemetry_history_rejects_invalid_time_range(api_client: TestClient) -> None:
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-invalid-range",
            timestamp="2026-01-01T10:00:00Z",
            value=10.0,
        ),
    )

    response = api_client.get(
        "/monitoring/assets/asset-1/telemetry",
        params={
            "start": "2026-01-01T12:00:00Z",
            "end": "2026-01-01T10:00:00Z",
        },
    )

    assert response.status_code == 422


def test_telemetry_latest_returns_newest_samples(api_client: TestClient) -> None:
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-latest-1",
            timestamp="2026-01-01T10:00:00Z",
            value=10.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-latest-2",
            timestamp="2026-01-01T11:00:00Z",
            value=11.0,
        ),
    )

    response = api_client.get(
        "/monitoring/assets/asset-1/telemetry/latest",
        params={"measurement_type": "temperature", "limit": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["samples"][-1]["value"] == 11.0


def test_telemetry_history_returns_404_for_unknown_asset(
    api_client: TestClient,
) -> None:
    response = api_client.get("/monitoring/assets/missing/telemetry")

    assert response.status_code == 404

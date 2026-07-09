"""Observation API endpoint specifications."""

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
    database_path = tmp_path / "observations_api.db"
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
    observation_id: str = "obs-api-1",
    asset_id: str = "asset-1",
    timestamp: str = "2026-01-01T12:00:00Z",
    measurement_type: str = "temperature",
    value: float = 42.5,
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


def test_create_observation_returns_202(api_client: TestClient) -> None:
    payload = _observation_payload()

    response = api_client.post("/observations", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["id"] == payload["id"]
    assert body["asset_id"] == payload["asset_id"]
    assert body["timestamp"] == payload["timestamp"]
    assert body["measurement_type"] == payload["measurement_type"]
    assert body["value"] == payload["value"]
    assert body["unit"] == payload["unit"]
    assert isinstance(body["job_id"], str)
    assert body["job_id"]


def test_create_observation_rejects_invalid_payload(api_client: TestClient) -> None:
    response = api_client.post(
        "/observations",
        json={
            "id": "",
            "asset_id": "asset-1",
            "timestamp": "2026-01-01T12:00:00Z",
            "measurement_type": "temperature",
            "value": 42.5,
            "unit": "celsius",
        },
    )

    assert response.status_code == 422


def test_create_observation_rejects_duplicate_id(api_client: TestClient) -> None:
    payload = _observation_payload(observation_id="obs-duplicate")
    api_client.post("/observations", json=payload)

    response = api_client.post("/observations", json=payload)

    assert response.status_code == 409


def test_list_observations_returns_all_in_stable_order(
    api_client: TestClient,
) -> None:
    first = _observation_payload(
        observation_id="obs-a",
        timestamp="2026-01-01T10:00:00Z",
        value=1.0,
    )
    second = _observation_payload(
        observation_id="obs-b",
        timestamp="2026-01-01T11:00:00Z",
        value=2.0,
    )
    third = _observation_payload(
        observation_id="obs-c",
        timestamp="2026-01-01T12:00:00Z",
        value=3.0,
    )
    api_client.post("/observations", json=third)
    api_client.post("/observations", json=first)
    api_client.post("/observations", json=second)

    response = api_client.get("/observations")

    assert response.status_code == 200
    assert response.json() == [first, second, third]


def test_get_observation_by_id(api_client: TestClient) -> None:
    payload = _observation_payload(observation_id="obs-get-one")
    api_client.post("/observations", json=payload)

    response = api_client.get("/observations/obs-get-one")

    assert response.status_code == 200
    assert response.json() == payload


def test_get_unknown_observation_returns_404(api_client: TestClient) -> None:
    response = api_client.get("/observations/missing-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "observation with id 'missing-id' not found"


def test_create_observation_triggers_reasoning_when_asset_has_sufficient_evidence(
    api_client: TestClient,
) -> None:
    from tests.backend.helpers import drain_reasoning_jobs

    first = _observation_payload(
        observation_id="obs-reason-api-1",
        timestamp="2026-01-01T10:00:00Z",
        value=30.0,
    )
    second = _observation_payload(
        observation_id="obs-reason-api-2",
        timestamp="2026-01-01T11:00:00Z",
        value=45.0,
    )

    first_response = api_client.post("/observations", json=first)
    second_response = api_client.post("/observations", json=second)

    assert first_response.status_code == 202
    assert second_response.status_code == 202
    assert first_response.json()["id"] == first["id"]
    assert second_response.json()["id"] == second["id"]
    assert first_response.json()["job_id"]
    assert second_response.json()["job_id"]

    drain_reasoning_jobs(api_client)

"""Monitoring API endpoint specifications."""

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
    database_path = tmp_path / "monitoring_api.db"
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


def test_list_assets_returns_known_assets(api_client: TestClient) -> None:
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-assets-1",
            asset_id="asset-a",
            timestamp="2026-01-01T10:00:00Z",
            value=10.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-assets-2",
            asset_id="asset-b",
            timestamp="2026-01-01T10:01:00Z",
            value=11.0,
        ),
    )

    response = api_client.get("/monitoring/assets")

    assert response.status_code == 200
    assert response.json() == [{"id": "asset-a"}, {"id": "asset-b"}]


def test_asset_history_returns_empty_list_when_no_reasoning_yet(
    api_client: TestClient,
) -> None:
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-empty-1",
            asset_id="asset-empty",
            timestamp="2026-01-01T10:00:00Z",
            value=30.0,
        ),
    )

    response = api_client.get("/monitoring/assets/asset-empty/history")

    assert response.status_code == 200
    assert response.json() == []


def test_asset_latest_returns_404_when_no_reasoning_history(
    api_client: TestClient,
) -> None:
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-latest-empty-1",
            asset_id="asset-no-history",
            timestamp="2026-01-01T10:00:00Z",
            value=30.0,
        ),
    )

    response = api_client.get("/monitoring/assets/asset-no-history/latest")

    assert response.status_code == 404
    assert (
        response.json()["detail"]
        == "asset with id 'asset-no-history' has no reasoning history"
    )


def test_unknown_asset_returns_404(api_client: TestClient) -> None:
    history = api_client.get("/monitoring/assets/missing-asset/history")
    latest = api_client.get("/monitoring/assets/missing-asset/latest")

    assert history.status_code == 404
    assert latest.status_code == 404
    assert history.json()["detail"] == "asset with id 'missing-asset' not found"
    assert latest.json()["detail"] == "asset with id 'missing-asset' not found"


def test_latest_and_history_ordering(api_client: TestClient) -> None:
    asset_id = "asset-ordered"
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-ord-1",
            asset_id=asset_id,
            timestamp="2026-01-01T10:00:00Z",
            value=30.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-ord-2",
            asset_id=asset_id,
            timestamp="2026-01-01T10:01:00Z",
            value=45.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-ord-3",
            asset_id=asset_id,
            timestamp="2026-01-01T10:02:00Z",
            value=50.0,
        ),
    )

    history_response = api_client.get(f"/monitoring/assets/{asset_id}/history")
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) >= 2

    timestamps = [item["timestamp"] for item in history]
    assert timestamps == sorted(timestamps)

    latest_response = api_client.get(f"/monitoring/assets/{asset_id}/latest")
    assert latest_response.status_code == 200
    assert latest_response.json()["run_id"] == history[-1]["run_id"]


def test_run_lookup_returns_complete_details(api_client: TestClient) -> None:
    asset_id = "asset-run"
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-run-1",
            asset_id=asset_id,
            timestamp="2026-01-01T10:00:00Z",
            value=30.0,
        ),
    )
    api_client.post(
        "/observations",
        json=_observation_payload(
            observation_id="obs-run-2",
            asset_id=asset_id,
            timestamp="2026-01-01T10:01:00Z",
            value=45.0,
        ),
    )

    history_response = api_client.get(f"/monitoring/assets/{asset_id}/history")
    assert history_response.status_code == 200
    run_id = history_response.json()[-1]["run_id"]

    response = api_client.get(f"/monitoring/runs/{run_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run_id
    assert len(payload["observations"]) == 2
    assert payload["reasoning_trace"] is not None
    assert len(payload["reasoning_trace"]["steps"]) == 11
    assert payload["structured_assessment"] is not None
    assert payload["operational_situation"] is not None
    assert payload["decision_context"] is not None
    assert payload["decision_plan"] is not None


def test_unknown_run_returns_404(api_client: TestClient) -> None:
    response = api_client.get("/monitoring/runs/missing-run")

    assert response.status_code == 404
    assert response.json()["detail"] == "reasoning run with id 'missing-run' not found"


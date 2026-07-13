"""Investigation transition API endpoint specifications."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.main import create_app
from tests.backend.helpers import drain_reasoning_jobs


@pytest.fixture
def sqlite_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "investigation_api.db"
    return Settings(
        database_url=f"sqlite:///{database_path}",
        forecast_enabled=False,
    )


@pytest.fixture
def api_client(sqlite_settings: Settings) -> Generator[TestClient, None, None]:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        yield client


def _seed_asset_with_recommendation(api_client: TestClient, asset_id: str) -> str:
    """Create enough observations to produce a recommendation; return its id."""
    observations = [
        {
            "id": f"obs-{asset_id}-1",
            "asset_id": asset_id,
            "timestamp": "2026-01-01T10:00:00Z",
            "measurement_type": "temperature",
            "value": 30.0,
            "unit": "celsius",
        },
        {
            "id": f"obs-{asset_id}-2",
            "asset_id": asset_id,
            "timestamp": "2026-01-01T11:00:00Z",
            "measurement_type": "temperature",
            "value": 45.0,
            "unit": "celsius",
        },
    ]
    for payload in observations:
        response = api_client.post("/observations", json=payload)
        assert response.status_code == 202

    drain_reasoning_jobs(api_client)

    recommendation = api_client.get(f"/monitoring/assets/{asset_id}/recommendation")
    assert recommendation.status_code == 200
    return str(recommendation.json()["id"])


def _transition_payload(
    *,
    recommendation_id: str,
    status: str = "ACKNOWLEDGED",
    actor_id: str = "j.operator",
    actor_display_name: str = "J. Operator",
    notes: str | None = None,
) -> dict[str, object]:
    return {
        "recommendation_id": recommendation_id,
        "status": status,
        "actor_id": actor_id,
        "actor_display_name": actor_display_name,
        "notes": notes,
    }


def test_record_transition_returns_201(api_client: TestClient) -> None:
    recommendation_id = _seed_asset_with_recommendation(api_client, "asset-inv-1")

    response = api_client.post(
        "/monitoring/assets/asset-inv-1/investigation",
        json=_transition_payload(recommendation_id=recommendation_id),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ACKNOWLEDGED"
    assert body["actor_id"] == "j.operator"
    assert body["actor_display_name"] == "J. Operator"
    assert body["recommendation_id"] == recommendation_id


def test_full_lifecycle_new_to_resolved(api_client: TestClient) -> None:
    recommendation_id = _seed_asset_with_recommendation(api_client, "asset-inv-2")

    acknowledge = api_client.post(
        "/monitoring/assets/asset-inv-2/investigation",
        json=_transition_payload(
            recommendation_id=recommendation_id, status="ACKNOWLEDGED"
        ),
    )
    assert acknowledge.status_code == 201

    investigating = api_client.post(
        "/monitoring/assets/asset-inv-2/investigation",
        json=_transition_payload(
            recommendation_id=recommendation_id, status="INVESTIGATING"
        ),
    )
    assert investigating.status_code == 201

    resolved = api_client.post(
        "/monitoring/assets/asset-inv-2/investigation",
        json=_transition_payload(
            recommendation_id=recommendation_id,
            status="RESOLVED",
            notes="Cooling loop restored",
        ),
    )
    assert resolved.status_code == 201
    assert resolved.json()["notes"] == "Cooling loop restored"

    twin = api_client.get("/monitoring/assets/asset-inv-2/digital-twin")
    assert twin.status_code == 200
    assert twin.json()["investigation"]["status"] == "RESOLVED"

    timeline = api_client.get("/monitoring/assets/asset-inv-2/timeline")
    assert timeline.status_code == 200
    transition_events = [
        event
        for event in timeline.json()
        if event["event_type"] == "investigation_transition"
    ]
    assert len(transition_events) == 3


def test_rejects_backward_transition_with_409(api_client: TestClient) -> None:
    recommendation_id = _seed_asset_with_recommendation(api_client, "asset-inv-3")

    api_client.post(
        "/monitoring/assets/asset-inv-3/investigation",
        json=_transition_payload(
            recommendation_id=recommendation_id, status="RESOLVED"
        ),
    )

    response = api_client.post(
        "/monitoring/assets/asset-inv-3/investigation",
        json=_transition_payload(
            recommendation_id=recommendation_id, status="ACKNOWLEDGED"
        ),
    )

    assert response.status_code == 409


def test_rejects_unknown_asset_with_404(api_client: TestClient) -> None:
    response = api_client.post(
        "/monitoring/assets/missing-asset/investigation",
        json=_transition_payload(recommendation_id="rec-does-not-matter"),
    )

    assert response.status_code == 404


def test_rejects_stale_recommendation_id_with_404(api_client: TestClient) -> None:
    _seed_asset_with_recommendation(api_client, "asset-inv-4")

    response = api_client.post(
        "/monitoring/assets/asset-inv-4/investigation",
        json=_transition_payload(recommendation_id="rec-does-not-exist"),
    )

    assert response.status_code == 404


def test_rejects_invalid_payload_with_422(api_client: TestClient) -> None:
    recommendation_id = _seed_asset_with_recommendation(api_client, "asset-inv-5")

    response = api_client.post(
        "/monitoring/assets/asset-inv-5/investigation",
        json=_transition_payload(
            recommendation_id=recommendation_id,
            status="BOGUS_STATUS",
        ),
    )

    assert response.status_code == 422

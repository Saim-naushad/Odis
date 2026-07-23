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


def test_lifecycle_survives_intervening_reasoning_cycles(
    api_client: TestClient,
) -> None:
    """Regression test for Issue 2: periodic reasoning updates must not
    invalidate an active operator investigation.

    Live testing found a recommendation regenerating on every reasoning
    cycle (every few seconds), each with a brand-new id, causing
    Acknowledge/Start investigating/Resolve to 404 against an
    already-superseded recommendation_id. This test seeds one
    recommendation_id up front (the way the frontend caches it) and then
    forces additional reasoning cycles - via new observations that don't
    change the asset's material classification - between every transition,
    proving the id (and the operator's in-flight investigation) survives
    them all the way through to RESOLVED.
    """
    asset_id = "asset-inv-lifecycle"
    recommendation_id = _seed_asset_with_recommendation(api_client, asset_id)

    def _advance_reasoning_cycle(sample_index: int) -> None:
        # A fresh observation timestamped later triggers a new reasoning
        # run (and previously, a new recommendation_id) without changing
        # the asset's underlying classification.
        response = api_client.post(
            "/observations",
            json={
                "id": f"obs-{asset_id}-cycle-{sample_index}",
                "asset_id": asset_id,
                "timestamp": f"2026-01-01T12:{sample_index:02d}:00Z",
                "measurement_type": "temperature",
                "value": 45.0,
                "unit": "celsius",
            },
        )
        assert response.status_code == 202
        drain_reasoning_jobs(api_client)

    _advance_reasoning_cycle(1)
    acknowledge = api_client.post(
        f"/monitoring/assets/{asset_id}/investigation",
        json=_transition_payload(
            recommendation_id=recommendation_id, status="ACKNOWLEDGED"
        ),
    )
    assert acknowledge.status_code == 201, acknowledge.json()

    _advance_reasoning_cycle(2)
    investigating = api_client.post(
        f"/monitoring/assets/{asset_id}/investigation",
        json=_transition_payload(
            recommendation_id=recommendation_id, status="INVESTIGATING"
        ),
    )
    assert investigating.status_code == 201, investigating.json()

    _advance_reasoning_cycle(3)
    resolved = api_client.post(
        f"/monitoring/assets/{asset_id}/investigation",
        json=_transition_payload(
            recommendation_id=recommendation_id, status="RESOLVED"
        ),
    )
    assert resolved.status_code == 201, resolved.json()

    twin = api_client.get(f"/monitoring/assets/{asset_id}/digital-twin")
    assert twin.status_code == 200
    assert twin.json()["investigation"]["status"] == "RESOLVED"

"""AI fault investigation read-model API specifications (PR179).

A known asset with no active/any AI-fault history is a normal
operational state (HTTP 200, null/empty), never a 404 — only an unknown
asset id or unknown investigation id is a 404. Uses `ReasoningBridgeService`
directly (mirroring `test_reasoning_bridge_service.py`) to seed evidence
rows against the same database the API's `TestClient` reads from, since
the real path (Kafka) is out of scope for this test.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from backend.app.application.reasoning_bridge.input_events import (
    ValidatedAlertTransition,
)
from backend.app.application.reasoning_bridge.reasoning_bridge_service import (
    ReasoningBridgeService,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.main import create_app

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_INCREASING = [10.0, 10.0, 10.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
_DECREASING = [70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0, 10.0, 10.0, 10.0]


@pytest.fixture
def sqlite_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "fault_investigation_api.db"
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


def _session_factory(api_client: TestClient) -> sessionmaker[Session]:
    factory = api_client.app.state.session_factory  # type: ignore[attr-defined]
    assert factory is not None
    return cast(sessionmaker[Session], factory)


def _seed_corroborating_observations(api_client: TestClient, asset_id: str) -> None:
    for i, value in enumerate(_INCREASING):
        timestamp = _T0 - timedelta(seconds=(len(_INCREASING) - i) * 10)
        response = api_client.post(
            "/observations",
            json={
                "id": f"obs-{asset_id}-stack_temperature-{i}",
                "asset_id": asset_id,
                "timestamp": timestamp.isoformat(),
                "measurement_type": "stack_temperature",
                "value": value,
                "unit": "celsius",
            },
        )
        assert response.status_code == 202
    for i, value in enumerate(_DECREASING):
        timestamp = _T0 - timedelta(seconds=(len(_DECREASING) - i) * 10)
        response = api_client.post(
            "/observations",
            json={
                "id": f"obs-{asset_id}-coolant_flow-{i}",
                "asset_id": asset_id,
                "timestamp": timestamp.isoformat(),
                "measurement_type": "coolant_flow",
                "value": value,
                "unit": "l/min",
            },
        )
        assert response.status_code == 202


def _alert_event(asset_id: str, **overrides: object) -> ValidatedAlertTransition:
    defaults: dict[str, object] = {
        "event_id": f"evt-{asset_id}-1",
        "event_version": "v1",
        "asset_id": asset_id,
        "source_timestamp": _T0,
        "transition_type": "confirmed",
        "from_state": "healthy",
        "to_state": "confirmed_cooling_degradation",
        "fault_class": "cooling_degradation",
        "diagnosed_class": "cooling_degradation",
        "evidence_items": ({"label": "x", "value": 1.0, "detail": "y"},),
        "model_system_version": "plant_alpha_fault_v1",
        "model_hash": "hash-a",
        "policy_hash": "policy-a",
        "feature_schema_version": "1.0",
        "class_scores": {"healthy": 0.05, "cooling_degradation": 0.9},
        "maximum_score": 0.9,
    }
    defaults.update(overrides)
    return ValidatedAlertTransition(**defaults)  # type: ignore[arg-type]


def _process_alert(
    api_client: TestClient, event: ValidatedAlertTransition
) -> None:
    session_factory = _session_factory(api_client)
    service = ReasoningBridgeService(lambda: SqlAlchemyUnitOfWork(session_factory))
    service.process_alert_transition(event)


def test_active_endpoint_returns_404_for_unknown_asset(
    api_client: TestClient,
) -> None:
    response = api_client.get("/monitoring/assets/does-not-exist/fault-investigation")
    assert response.status_code == 404


def test_active_endpoint_returns_200_null_for_known_asset_with_no_history(
    api_client: TestClient,
) -> None:
    asset_id = "asset-fi-no-history"
    _seed_corroborating_observations(api_client, asset_id)

    response = api_client.get(f"/monitoring/assets/{asset_id}/fault-investigation")

    assert response.status_code == 200
    assert response.json() == {"active_investigation": None}


def test_active_endpoint_returns_200_null_when_latest_investigation_is_cleared(
    api_client: TestClient,
) -> None:
    asset_id = "asset-fi-cleared"
    _seed_corroborating_observations(api_client, asset_id)
    _process_alert(api_client, _alert_event(asset_id))
    _process_alert(
        api_client,
        _alert_event(
            asset_id,
            event_id=f"evt-{asset_id}-2",
            transition_type="cleared",
            from_state="confirmed_cooling_degradation",
            to_state="healthy",
            diagnosed_class="healthy",
            source_timestamp=_T0 + timedelta(seconds=10),
        ),
    )

    response = api_client.get(f"/monitoring/assets/{asset_id}/fault-investigation")

    assert response.status_code == 200
    assert response.json() == {"active_investigation": None}


def test_active_endpoint_returns_populated_result_for_an_open_investigation(
    api_client: TestClient,
) -> None:
    asset_id = "asset-fi-active"
    _seed_corroborating_observations(api_client, asset_id)
    _process_alert(api_client, _alert_event(asset_id))

    response = api_client.get(f"/monitoring/assets/{asset_id}/fault-investigation")

    assert response.status_code == 200
    body = response.json()
    active = body["active_investigation"]
    assert active is not None
    assert active["asset_id"] == asset_id
    assert active["investigation_status"] == "OPEN"
    assert active["diagnosed_fault_class"] == "cooling_degradation"
    assert active["corroboration_result"] == "corroborated"
    assert active["recommendation"] is not None
    assert active["recommendation"]["status"] == "produced"
    assert active["authority_boundary_note"]
    assert len(active["supporting_evidence"]) > 0
    assert active["provenance"]["latest_model_score"] == pytest.approx(0.9)
    assert active["provenance"]["score_semantics"]


def test_active_endpoint_never_exposes_forbidden_model_internals(
    api_client: TestClient,
) -> None:
    asset_id = "asset-fi-safe"
    _seed_corroborating_observations(api_client, asset_id)
    _process_alert(api_client, _alert_event(asset_id))

    response = api_client.get(f"/monitoring/assets/{asset_id}/fault-investigation")

    assert response.status_code == 200
    assert "class_scores" not in response.text
    assert "evidence_items" not in response.text


def test_history_endpoint_returns_empty_list_for_known_asset_with_no_history(
    api_client: TestClient,
) -> None:
    asset_id = "asset-fi-history-empty"
    _seed_corroborating_observations(api_client, asset_id)

    response = api_client.get(f"/monitoring/assets/{asset_id}/fault-investigations")

    assert response.status_code == 200
    assert response.json() == []


def test_history_endpoint_returns_404_for_unknown_asset(api_client: TestClient) -> None:
    response = api_client.get("/monitoring/assets/does-not-exist/fault-investigations")
    assert response.status_code == 404


def test_history_endpoint_counts_investigations_not_rows(
    api_client: TestClient,
) -> None:
    """A multi-transition investigation must not crowd out an older,
    separate investigation when `limit` is small."""
    asset_id = "asset-fi-history-grouping"
    _seed_corroborating_observations(api_client, asset_id)

    # First investigation: confirmed -> cleared (2 rows, same investigation).
    _process_alert(api_client, _alert_event(asset_id, event_id="evt-1"))
    _process_alert(
        api_client,
        _alert_event(
            asset_id,
            event_id="evt-2",
            transition_type="cleared",
            from_state="confirmed_cooling_degradation",
            to_state="healthy",
            diagnosed_class="healthy",
            source_timestamp=_T0 + timedelta(seconds=10),
        ),
    )
    # Second, separate investigation.
    _process_alert(
        api_client,
        _alert_event(
            asset_id,
            event_id="evt-3",
            source_timestamp=_T0 + timedelta(seconds=20),
        ),
    )

    response = api_client.get(
        f"/monitoring/assets/{asset_id}/fault-investigations", params={"limit": 1}
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["investigation_status"] == "OPEN"


def test_detail_endpoint_returns_full_lifecycle(api_client: TestClient) -> None:
    asset_id = "asset-fi-detail"
    _seed_corroborating_observations(api_client, asset_id)
    first = _alert_event(asset_id, event_id="evt-1")
    _process_alert(api_client, first)
    _process_alert(
        api_client,
        _alert_event(
            asset_id,
            event_id="evt-2",
            transition_type="class_changed",
            from_state="confirmed_cooling_degradation",
            to_state="confirmed_hydrogen_supply_issue",
            fault_class="hydrogen_supply_issue",
            diagnosed_class="hydrogen_supply_issue",
            source_timestamp=_T0 + timedelta(seconds=10),
        ),
    )

    active = api_client.get(f"/monitoring/assets/{asset_id}/fault-investigation")
    investigation_id = active.json()["active_investigation"]["investigation_id"]

    response = api_client.get(f"/monitoring/fault-investigations/{investigation_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["investigation_id"] == investigation_id
    assert body["current"]["diagnosed_fault_class"] == "hydrogen_supply_issue"
    assert len(body["timeline"]) == 2
    assert body["timeline"][0]["diagnosed_fault_class"] == "cooling_degradation"
    assert body["timeline"][1]["diagnosed_fault_class"] == "hydrogen_supply_issue"


def test_detail_endpoint_returns_404_for_unknown_investigation(
    api_client: TestClient,
) -> None:
    response = api_client.get("/monitoring/fault-investigations/does-not-exist")
    assert response.status_code == 404

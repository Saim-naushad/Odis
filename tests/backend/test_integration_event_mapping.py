from __future__ import annotations

from datetime import UTC, datetime

from backend.app.application.events.domain_events import (
    HealthChanged,
    InvestigationTransitionRecorded,
    NotificationCreated,
    ReasoningCompleted,
    RecommendationUpdated,
    RiskChanged,
    TrendChanged,
)
from backend.app.application.integration_event_mapping import (
    map_domain_event_to_integration_event,
)


def test_mapping_skips_unmapped_events() -> None:
    assert map_domain_event_to_integration_event(object()) is None


def test_mapping_reasoning_completed_to_digital_twin_updated() -> None:
    event = ReasoningCompleted(
        asset_id="asset-1",
        run_id="run-1",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )

    integration = map_domain_event_to_integration_event(event)

    assert integration is not None
    assert integration.type == "DigitalTwinUpdated"
    assert integration.payload["asset_id"] == "asset-1"
    assert integration.payload["run_id"] == "run-1"


def test_mapping_operational_state_changes() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    events = [
        HealthChanged(
            asset_id="asset-1",
            run_id="run-1",
            previous_health_status="NORMAL",
            new_health_status="WARNING",
            health_score=70,
            timestamp=timestamp,
        ),
        RiskChanged(
            asset_id="asset-1",
            run_id="run-1",
            previous_risk_level="LOW",
            new_risk_level="MEDIUM",
            health_score=70,
            timestamp=timestamp,
        ),
        TrendChanged(
            asset_id="asset-1",
            run_id="run-1",
            previous_direction="stable",
            new_direction="rising",
            stability_score=80,
            volatility_score=20,
            timestamp=timestamp,
        ),
        RecommendationUpdated(
            asset_id="asset-1",
            run_id="run-1",
            previous_recommendation="monitor",
            new_recommendation="inspect",
            timestamp=timestamp,
        ),
    ]

    for domain_event in events:
        integration = map_domain_event_to_integration_event(domain_event)
        assert integration is not None
        assert integration.type == "OperationalStateChanged"
        assert integration.payload["asset_id"] == "asset-1"
        assert integration.payload["run_id"] == "run-1"
        assert "change_type" in integration.payload


def test_mapping_notification_created_to_notification_raised() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    event = NotificationCreated(
        asset_id="asset-1",
        run_id="run-1",
        notification_id="notif-1",
        recommendation_id="rec-1",
        severity="INFO",
        status="ACTIVE",
        title="Alert",
        message="Hello",
        created_at=timestamp,
        timestamp=timestamp,
    )

    integration = map_domain_event_to_integration_event(event)

    assert integration is not None
    assert integration.type == "NotificationRaised"
    assert integration.payload["notification_id"] == "notif-1"


def test_mapping_investigation_transition_recorded() -> None:
    occurred_at = datetime(2026, 1, 1, tzinfo=UTC)
    event = InvestigationTransitionRecorded(
        asset_id="asset-1",
        recommendation_id="rec-1",
        transition_id="inv-1",
        status="ACKNOWLEDGED",
        actor_id="op-1",
        actor_display_name="Operator One",
        occurred_at=occurred_at,
        notes="Paged on-call",
        timestamp=occurred_at,
    )

    integration = map_domain_event_to_integration_event(event)

    assert integration is not None
    assert integration.type == "InvestigationTransitionRecorded"
    assert integration.payload["recommendation_id"] == "rec-1"
    assert integration.payload["status"] == "ACKNOWLEDGED"
    assert integration.payload["notes"] == "Paged on-call"


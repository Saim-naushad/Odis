from __future__ import annotations

from datetime import UTC, datetime

from backend.app.application.notification_policy_engine import NotificationPolicyEngine
from backend.app.application.recommendation_engine import RecommendationEngine
from backend.app.domain.operational_state import OperationalState


def _state(
    *, health_status: str, risk_level: str, health_score: int
) -> OperationalState:
    return OperationalState(
        asset_id="asset-1",
        health_score=health_score,
        health_status=health_status,  # type: ignore[arg-type]
        risk_level=risk_level,  # type: ignore[arg-type]
        confidence=70,
        primary_driver="Decision priority: high",
        recommended_action="Investigate operational conditions",
        last_updated=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
    )


def test_confirmed_critical_health_is_p0_and_critical_severity() -> None:
    state = _state(health_status="CRITICAL", risk_level="HIGH", health_score=30)
    recommendation = RecommendationEngine().compute(state)

    assert recommendation.priority == "P0"
    assert recommendation.title == "Immediate mitigation required"

    notification = NotificationPolicyEngine().compute(recommendation)
    assert notification is not None
    assert notification.severity == "CRITICAL"


def test_elevated_risk_without_critical_health_is_p1_not_critical_severity() -> None:
    """Regression test for the NORMAL/WARNING + CRITICAL-banner contradiction.

    risk_level can read HIGH from decision priority alone before
    health_score/health_status has caught up to a CRITICAL reading
    (OperationalStateEngine's risk_level is a deliberate leading indicator).
    Before this fix, that alone produced a "CRITICAL / Immediate mitigation
    required" notification even when health_status was only WARNING (never
    CRITICAL) - overclaiming severity relative to the asset's actual health.
    """
    state = _state(health_status="WARNING", risk_level="HIGH", health_score=45)
    recommendation = RecommendationEngine().compute(state)

    assert recommendation.priority == "P1"
    assert recommendation.title != "Immediate mitigation required"
    assert "WARNING" in recommendation.description

    notification = NotificationPolicyEngine().compute(recommendation)
    assert notification is not None
    assert notification.severity == "WARNING"
    assert notification.severity != "CRITICAL"


def test_warning_health_without_high_risk_is_p2() -> None:
    state = _state(health_status="WARNING", risk_level="MEDIUM", health_score=60)
    recommendation = RecommendationEngine().compute(state)

    assert recommendation.priority == "P2"

    notification = NotificationPolicyEngine().compute(recommendation)
    assert notification is not None
    assert notification.severity == "WARNING"


def test_normal_low_risk_produces_no_notification() -> None:
    state = _state(health_status="NORMAL", risk_level="LOW", health_score=90)
    recommendation = RecommendationEngine().compute(state)

    assert recommendation.priority == "P3"
    assert NotificationPolicyEngine().compute(recommendation) is None


def test_recommendation_id_is_stable_across_reasoning_cycles() -> None:
    """Regression test for Issue 2's root cause: recommendation identity
    must not change just because a new reasoning cycle ran - only when the
    recommendation's material classification actually changes."""
    first = RecommendationEngine().compute(
        _state(health_status="WARNING", risk_level="HIGH", health_score=45)
    )
    second_state = OperationalState(
        asset_id="asset-1",
        health_score=45,
        health_status="WARNING",
        risk_level="HIGH",
        confidence=72,  # confidence/timestamp drift between cycles...
        primary_driver="Decision priority: high",
        recommended_action="Investigate operational conditions",
        last_updated=datetime(2026, 1, 1, 10, 0, 4, tzinfo=UTC),  # ...4s later
    )
    second = RecommendationEngine().compute(second_state)

    assert first.id == second.id


def test_recommendation_id_changes_when_classification_materially_changes() -> None:
    high_risk = RecommendationEngine().compute(
        _state(health_status="WARNING", risk_level="HIGH", health_score=45)
    )
    recovered = RecommendationEngine().compute(
        _state(health_status="NORMAL", risk_level="LOW", health_score=90)
    )

    assert high_risk.id != recovered.id

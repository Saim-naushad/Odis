from datetime import UTC, datetime

import pytest

from backend.app.application.notification_policy_engine import NotificationPolicyEngine
from backend.app.domain.recommendation import Recommendation


def _recommendation(*, priority: str) -> Recommendation:
    return Recommendation(
        id=f"rec-asset-1-20260101T100000Z-{priority}",
        asset_id="asset-1",
        category="investigate",
        priority=priority,  # type: ignore[arg-type]
        urgency="SOON",
        title="Test recommendation",
        description="Test description",
        recommended_steps=("Step 1",),
        estimated_impact="Test impact",
        created_at=datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("priority", "expected"),
    [
        ("P0", "CRITICAL"),
        ("P1", "WARNING"),
        ("P2", "WARNING"),
    ],
)
def test_policy_creates_notification_for_p0_p1_p2(
    priority: str, expected: str
) -> None:
    engine = NotificationPolicyEngine()
    notification = engine.compute(_recommendation(priority=priority))
    assert notification is not None
    assert notification.severity == expected
    assert notification.status == "OPEN"
    assert notification.recommendation_id.startswith("rec-")


def test_only_p0_is_critical_severity() -> None:
    # P1 is elevated risk that has not been confirmed as a CRITICAL health
    # reading (see RecommendationEngine.compute()) - it must read WARNING,
    # not CRITICAL, so the notification never overclaims severity relative
    # to the underlying health status.
    engine = NotificationPolicyEngine()
    assert engine.compute(_recommendation(priority="P0")).severity == "CRITICAL"  # type: ignore[union-attr]
    assert engine.compute(_recommendation(priority="P1")).severity == "WARNING"  # type: ignore[union-attr]


def test_policy_returns_none_for_p3() -> None:
    engine = NotificationPolicyEngine()
    assert engine.compute(_recommendation(priority="P3")) is None


"""Deterministic mapping Recommendation -> Notification (or None)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.notification import Notification, NotificationSeverity
from backend.app.domain.recommendation import Recommendation


@dataclass(frozen=True, slots=True)
class NotificationPolicyEngine:
    """Compute a Notification from a Recommendation only."""

    def compute(self, recommendation: Recommendation) -> Notification | None:
        # P0 is a confirmed CRITICAL health reading; P1 is elevated risk
        # (decision priority alone) that has not yet been confirmed as a
        # CRITICAL health reading - see RecommendationEngine.compute(). They
        # must not share a severity label, or the notification claims
        # "CRITICAL" for a state that may currently read NORMAL or WARNING.
        severity: NotificationSeverity
        if recommendation.priority == "P0":
            severity = "CRITICAL"
        elif recommendation.priority in ("P1", "P2"):
            severity = "WARNING"
        else:
            return None

        notification_id = f"notif-{recommendation.id}"
        return Notification(
            id=notification_id,
            asset_id=recommendation.asset_id,
            recommendation_id=recommendation.id,
            severity=severity,
            status="OPEN",
            title=recommendation.title,
            message=recommendation.description,
            created_at=recommendation.created_at,
        )


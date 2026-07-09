"""Deterministic mapping Recommendation -> Notification (or None)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.notification import Notification, NotificationSeverity
from backend.app.domain.recommendation import Recommendation


@dataclass(frozen=True, slots=True)
class NotificationPolicyEngine:
    """Compute a Notification from a Recommendation only."""

    def compute(self, recommendation: Recommendation) -> Notification | None:
        severity: NotificationSeverity
        if recommendation.priority in ("P0", "P1"):
            severity = "CRITICAL"
        elif recommendation.priority == "P2":
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


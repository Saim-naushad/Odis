"""Notification domain model.

Notifications are operator-facing business objects created deterministically
from Recommendations via the NotificationPolicyEngine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

NotificationSeverity = Literal["INFO", "WARNING", "CRITICAL"]
NotificationStatus = Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]


@dataclass(frozen=True, slots=True)
class Notification:
    """Immutable notification for an asset at a point in time."""

    id: str
    asset_id: str
    recommendation_id: str
    severity: NotificationSeverity
    status: NotificationStatus
    title: str
    message: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not self.recommendation_id:
            raise ValueError("recommendation_id must not be empty")
        if self.severity not in ("INFO", "WARNING", "CRITICAL"):
            raise ValueError("severity must be one of: INFO, WARNING, CRITICAL")
        if self.status not in ("OPEN", "ACKNOWLEDGED", "RESOLVED"):
            raise ValueError("status must be one of: OPEN, ACKNOWLEDGED, RESOLVED")
        if not self.title:
            raise ValueError("title must not be empty")
        if not self.message:
            raise ValueError("message must not be empty")


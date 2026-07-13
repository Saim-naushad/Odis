"""Operational investigation timeline primitives.

Timeline events record meaningful operational milestones for an asset so
operators can understand how the system reached its current conclusions.
This is not an audit log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

TimelineEventType = Literal[
    "observation_received",
    "reasoning_started",
    "reasoning_completed",
    "recommendation_updated",
    "notification_created",
    "trend_changed",
    "health_changed",
    "risk_changed",
    "investigation_transition",
]


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    """Immutable operational event in an asset investigation timeline."""

    id: str
    asset_id: str
    timestamp: datetime
    event_type: TimelineEventType
    title: str
    description: str
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not self.title:
            raise ValueError("title must not be empty")
        if not self.description:
            raise ValueError("description must not be empty")

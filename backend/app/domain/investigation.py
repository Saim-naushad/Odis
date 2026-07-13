"""Investigation lifecycle domain model.

An investigation transition records an operator's response to a
Recommendation (acknowledging it, starting an investigation, resolving it).
Transitions are append-only: each operator action produces a new immutable
record rather than mutating previous state. The absence of any transition
means the recommendation is implicitly NEW; the current status for a
recommendation is the most recent transition on record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

InvestigationStatus = Literal["ACKNOWLEDGED", "INVESTIGATING", "RESOLVED"]

INVESTIGATION_STATUS_ORDER: tuple[InvestigationStatus, ...] = (
    "ACKNOWLEDGED",
    "INVESTIGATING",
    "RESOLVED",
)


@dataclass(frozen=True, slots=True)
class InvestigationEvent:
    """Immutable record of a single operator investigation transition."""

    id: str
    asset_id: str
    recommendation_id: str
    status: InvestigationStatus
    actor_id: str
    actor_display_name: str
    occurred_at: datetime
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not self.recommendation_id:
            raise ValueError("recommendation_id must not be empty")
        if self.status not in INVESTIGATION_STATUS_ORDER:
            raise ValueError(
                "status must be one of: " + ", ".join(INVESTIGATION_STATUS_ORDER)
            )
        if not self.actor_id:
            raise ValueError("actor_id must not be empty")
        if not self.actor_display_name:
            raise ValueError("actor_display_name must not be empty")

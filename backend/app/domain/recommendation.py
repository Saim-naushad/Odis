"""Recommendation domain model.

A Recommendation is an operator-facing, structured policy output derived
deterministically from an OperationalState. It is not a reasoning artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

RecommendationCategory = Literal[
    "investigate",
    "mitigate",
    "monitor",
]
RecommendationPriority = Literal["P0", "P1", "P2", "P3"]
RecommendationUrgency = Literal["IMMEDIATE", "SOON", "SCHEDULED"]


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Immutable recommendation for an asset at a point in time."""

    id: str
    asset_id: str
    category: RecommendationCategory
    priority: RecommendationPriority
    urgency: RecommendationUrgency
    title: str
    description: str
    recommended_steps: tuple[str, ...]
    estimated_impact: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if self.category not in ("investigate", "mitigate", "monitor"):
            raise ValueError("category must be one of: investigate, mitigate, monitor")
        if self.priority not in ("P0", "P1", "P2", "P3"):
            raise ValueError("priority must be one of: P0, P1, P2, P3")
        if self.urgency not in ("IMMEDIATE", "SOON", "SCHEDULED"):
            raise ValueError("urgency must be one of: IMMEDIATE, SOON, SCHEDULED")
        if not self.title:
            raise ValueError("title must not be empty")
        if not self.description:
            raise ValueError("description must not be empty")
        if not self.recommended_steps:
            raise ValueError("recommended_steps must not be empty")
        if any(not step for step in self.recommended_steps):
            raise ValueError("recommended_steps must not contain empty entries")
        if not self.estimated_impact:
            raise ValueError("estimated_impact must not be empty")


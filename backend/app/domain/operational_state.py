"""Operational State domain model.

The Operational State is the operator-facing summary of an asset's current
condition. It is derived deterministically from existing reasoning artifacts
(decision plan, explainable reasoning, and trend analysis) and does not introduce
any prediction, ML, or probabilistic forecasting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

HealthStatus = Literal["NORMAL", "WARNING", "CRITICAL"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True, slots=True)
class OperationalState:
    """Immutable operational condition for an asset at a point in time."""

    asset_id: str
    health_score: int  # 0..100
    health_status: HealthStatus
    risk_level: RiskLevel
    confidence: int  # 0..100 (derived from explainable reasoning confidence)
    primary_driver: str
    recommended_action: str
    last_updated: datetime

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not (0 <= self.health_score <= 100):
            raise ValueError("health_score must be between 0 and 100")
        if self.health_status not in ("NORMAL", "WARNING", "CRITICAL"):
            raise ValueError("health_status must be one of: NORMAL, WARNING, CRITICAL")
        if self.risk_level not in ("LOW", "MEDIUM", "HIGH"):
            raise ValueError("risk_level must be one of: LOW, MEDIUM, HIGH")
        if not (0 <= self.confidence <= 100):
            raise ValueError("confidence must be between 0 and 100")
        if not self.primary_driver:
            raise ValueError("primary_driver must not be empty")
        if not self.recommended_action:
            raise ValueError("recommended_action must not be empty")


"""Domain events emitted by application services.

These events contain only domain-relevant information and are intended to be
handled in-process by application-level handlers (e.g. monitoring publication).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ObservationCreated:
    asset_id: str
    observation_id: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class ReasoningCompleted:
    asset_id: str
    run_id: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class ReasoningStarted:
    asset_id: str
    run_id: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class RecommendationUpdated:
    asset_id: str
    run_id: str
    previous_recommendation: str | None
    new_recommendation: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class TrendChanged:
    asset_id: str
    run_id: str
    previous_direction: str
    new_direction: str
    stability_score: int
    volatility_score: int
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class HealthChanged:
    asset_id: str
    run_id: str
    previous_health_status: str
    new_health_status: str
    health_score: int
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class RiskChanged:
    asset_id: str
    run_id: str
    previous_risk_level: str
    new_risk_level: str
    health_score: int
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class NotificationCreated:
    asset_id: str
    run_id: str
    notification_id: str
    recommendation_id: str
    severity: str
    status: str
    title: str
    message: str
    created_at: datetime
    timestamp: datetime


"""Mapping between domain events and integration events.

Only a curated subset of domain events should cross the integration boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from backend.app.application.events.domain_events import (
    HealthChanged,
    NotificationCreated,
    ReasoningCompleted,
    RecommendationUpdated,
    RiskChanged,
    TrendChanged,
)
from backend.app.application.integration_events import IntegrationEvent


def map_domain_event_to_integration_event(event: object) -> IntegrationEvent | None:
    """Return a mapped IntegrationEvent or None when no mapping exists."""

    occurred_at = _event_timestamp(event)

    if isinstance(event, ReasoningCompleted):
        return IntegrationEvent(
            id=str(uuid4()),
            type="DigitalTwinUpdated",
            occurred_at=occurred_at,
            payload={
                "asset_id": event.asset_id,
                "run_id": event.run_id,
                "timestamp": _to_iso(occurred_at),
            },
        )

    if isinstance(
        event,
        (HealthChanged, RiskChanged, TrendChanged, RecommendationUpdated),
    ):
        return IntegrationEvent(
            id=str(uuid4()),
            type="OperationalStateChanged",
            occurred_at=occurred_at,
            payload=_operational_state_payload(event, occurred_at),
        )

    if isinstance(event, NotificationCreated):
        return IntegrationEvent(
            id=str(uuid4()),
            type="NotificationRaised",
            occurred_at=occurred_at,
            payload={
                "asset_id": event.asset_id,
                "run_id": event.run_id,
                "notification_id": event.notification_id,
                "recommendation_id": event.recommendation_id,
                "severity": event.severity,
                "status": event.status,
                "title": event.title,
                "message": event.message,
                "created_at": _to_iso(event.created_at),
                "timestamp": _to_iso(occurred_at),
            },
        )

    return None


def _event_timestamp(event: object) -> datetime:
    raw = getattr(event, "timestamp", None)
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=UTC)
        return raw
    return datetime.now(UTC)


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _operational_state_payload(event: object, occurred_at: datetime) -> dict[str, Any]:
    base: dict[str, Any] = {
        "asset_id": str(getattr(event, "asset_id", "")),
        "run_id": str(getattr(event, "run_id", "")),
        "timestamp": _to_iso(occurred_at),
    }

    if isinstance(event, HealthChanged):
        base.update(
            {
                "change_type": "health_status",
                "previous_health_status": event.previous_health_status,
                "new_health_status": event.new_health_status,
                "health_score": event.health_score,
            }
        )
        return base

    if isinstance(event, RiskChanged):
        base.update(
            {
                "change_type": "risk_level",
                "previous_risk_level": event.previous_risk_level,
                "new_risk_level": event.new_risk_level,
                "health_score": event.health_score,
            }
        )
        return base

    if isinstance(event, TrendChanged):
        base.update(
            {
                "change_type": "trend_direction",
                "previous_direction": event.previous_direction,
                "new_direction": event.new_direction,
                "stability_score": event.stability_score,
                "volatility_score": event.volatility_score,
            }
        )
        return base

    if isinstance(event, RecommendationUpdated):
        base.update(
            {
                "change_type": "recommendation",
                "previous_recommendation": event.previous_recommendation,
                "new_recommendation": event.new_recommendation,
            }
        )
        return base

    base["change_type"] = type(event).__name__
    return base


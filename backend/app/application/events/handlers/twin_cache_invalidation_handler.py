"""Invalidate Digital Twin cache entries when underlying projections change."""

from __future__ import annotations

from backend.app.application.digital_twin_cache import DigitalTwinCache
from backend.app.application.events.domain_events import (
    HealthChanged,
    NotificationCreated,
    ReasoningCompleted,
    RecommendationUpdated,
    RiskChanged,
)


class DigitalTwinCacheInvalidationHandler:
    """Drop cached Digital Twins when monitored projections change."""

    def __init__(self, cache: DigitalTwinCache) -> None:
        self._cache = cache

    def on_health_changed(self, event: HealthChanged) -> None:
        self._invalidate(event.asset_id)

    def on_risk_changed(self, event: RiskChanged) -> None:
        self._invalidate(event.asset_id)

    def on_recommendation_updated(self, event: RecommendationUpdated) -> None:
        self._invalidate(event.asset_id)

    def on_notification_created(self, event: NotificationCreated) -> None:
        self._invalidate(event.asset_id)

    def on_reasoning_completed(self, event: ReasoningCompleted) -> None:
        # Operational state is recomputed on every reasoning run; health and risk
        # events only cover a subset of state transitions.
        self._invalidate(event.asset_id)

    def _invalidate(self, asset_id: str) -> None:
        self._cache.invalidate(asset_id)

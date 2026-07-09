"""Dispatch persisted outbox events via the in-process DomainEventBus."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.application.events.domain_events import (
    HealthChanged,
    NotificationCreated,
    ObservationCreated,
    ReasoningCompleted,
    ReasoningStarted,
    RecommendationUpdated,
    RiskChanged,
    TrendChanged,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.integration_event_mapping import (
    map_domain_event_to_integration_event,
)
from backend.app.application.integration_event_publisher import (
    IntegrationEventPublisher,
)
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.outbox import OutboxEvent
from backend.app.infrastructure.logging import get_logger

logger = get_logger(__name__)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _deserialize_domain_event(
    event_type: str,
    payload: dict[str, Any],
) -> object | None:
    if event_type == "ObservationCreated":
        return ObservationCreated(
            asset_id=str(payload["asset_id"]),
            observation_id=str(payload["observation_id"]),
            timestamp=_parse_datetime(str(payload["timestamp"])),
        )
    if event_type == "ReasoningCompleted":
        return ReasoningCompleted(
            asset_id=str(payload["asset_id"]),
            run_id=str(payload["run_id"]),
            timestamp=_parse_datetime(str(payload["timestamp"])),
        )
    if event_type == "ReasoningStarted":
        return ReasoningStarted(
            asset_id=str(payload["asset_id"]),
            run_id=str(payload["run_id"]),
            timestamp=_parse_datetime(str(payload["timestamp"])),
        )
    if event_type == "RecommendationUpdated":
        previous = payload.get("previous_recommendation")
        return RecommendationUpdated(
            asset_id=str(payload["asset_id"]),
            run_id=str(payload["run_id"]),
            previous_recommendation=(
                str(previous) if previous is not None else None
            ),
            new_recommendation=str(payload["new_recommendation"]),
            timestamp=_parse_datetime(str(payload["timestamp"])),
        )
    if event_type == "TrendChanged":
        return TrendChanged(
            asset_id=str(payload["asset_id"]),
            run_id=str(payload["run_id"]),
            previous_direction=str(payload["previous_direction"]),
            new_direction=str(payload["new_direction"]),
            stability_score=int(payload.get("stability_score", 0)),
            volatility_score=int(payload.get("volatility_score", 0)),
            timestamp=_parse_datetime(str(payload["timestamp"])),
        )
    if event_type == "HealthChanged":
        return HealthChanged(
            asset_id=str(payload["asset_id"]),
            run_id=str(payload["run_id"]),
            previous_health_status=str(payload["previous_health_status"]),
            new_health_status=str(payload["new_health_status"]),
            health_score=int(payload.get("health_score", 0)),
            timestamp=_parse_datetime(str(payload["timestamp"])),
        )
    if event_type == "RiskChanged":
        return RiskChanged(
            asset_id=str(payload["asset_id"]),
            run_id=str(payload["run_id"]),
            previous_risk_level=str(payload["previous_risk_level"]),
            new_risk_level=str(payload["new_risk_level"]),
            health_score=int(payload.get("health_score", 0)),
            timestamp=_parse_datetime(str(payload["timestamp"])),
        )
    if event_type == "NotificationCreated":
        return NotificationCreated(
            asset_id=str(payload["asset_id"]),
            run_id=str(payload["run_id"]),
            notification_id=str(payload["notification_id"]),
            recommendation_id=str(payload["recommendation_id"]),
            severity=str(payload["severity"]),
            status=str(payload["status"]),
            title=str(payload["title"]),
            message=str(payload["message"]),
            created_at=_parse_datetime(str(payload["created_at"])),
            timestamp=_parse_datetime(str(payload["timestamp"])),
        )
    return None


class OutboxDispatcher:
    """Load undispatched OutboxEvent rows and publish them."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork[Session]],
        event_bus: DomainEventBus,
        integration_event_publisher: IntegrationEventPublisher | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._event_bus = event_bus
        self._integration_event_publisher = integration_event_publisher

    def dispatch(self) -> None:
        """Publish any undispatched events and mark them dispatched."""
        now = datetime.now(UTC)
        published_any = False
        with self._unit_of_work_factory() as uow:
            session = uow.session
            events = list(
                session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.dispatched_at.is_(None))
                    .order_by(OutboxEvent.created_at.asc())
                )
            )
            for row in events:
                domain_event = _deserialize_domain_event(row.event_type, row.payload)
                if domain_event is None:
                    logger.info(
                        "outbox_event_skipped",
                        outbox_event_id=row.id,
                        event_type=row.event_type,
                    )
                    continue
                self._event_bus.publish(domain_event)
                self._publish_integration_event(domain_event)
                row.dispatched_at = now
                published_any = True
            if published_any:
                uow.commit()

    def _publish_integration_event(self, domain_event: object) -> None:
        publisher = self._integration_event_publisher
        if publisher is None:
            return
        integration_event = map_domain_event_to_integration_event(domain_event)
        if integration_event is None:
            return
        try:
            publisher.publish(integration_event)
        except Exception:
            # Integration boundary must never fail requests.
            logger.warning(
                "integration_event_publish_failed",
                domain_event_type=type(domain_event).__name__,
                integration_event_type=integration_event.type,
                integration_event_id=integration_event.id,
                exc_info=True,
            )


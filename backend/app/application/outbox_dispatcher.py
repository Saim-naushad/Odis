"""Dispatch persisted outbox events via the in-process DomainEventBus."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.application.events.domain_events import (
    ObservationCreated,
    ReasoningCompleted,
    ReasoningStarted,
    RecommendationUpdated,
    TrendChanged,
)
from backend.app.application.events.event_bus import DomainEventBus
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
    return None


class OutboxDispatcher:
    """Load undispatched OutboxEvent rows and publish them."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork[Session]],
        event_bus: DomainEventBus,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._event_bus = event_bus

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
                row.dispatched_at = now
                published_any = True
            if published_any:
                uow.commit()


"""Persist operational timeline events in response to domain events."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.app.application.events.domain_events import (
    ObservationCreated,
    ReasoningCompleted,
    ReasoningStarted,
    RecommendationUpdated,
    TrendChanged,
)
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.timeline import TimelineEvent
from backend.app.infrastructure.repositories.timeline_repository import (
    SqlAlchemyTimelineRepository,
)


class TimelineEventHandler:
    """Record investigation timeline events when domain events are published."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork[Session]],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def on_observation_created(self, event: ObservationCreated) -> None:
        self._record(
            TimelineEvent(
                id=str(uuid4()),
                asset_id=event.asset_id,
                timestamp=event.timestamp,
                event_type="observation_received",
                title="Observation received",
                description=(
                    f"New observation {event.observation_id} recorded for the asset."
                ),
                metadata={"observation_id": event.observation_id},
            )
        )

    def on_reasoning_started(self, event: ReasoningStarted) -> None:
        self._record(
            TimelineEvent(
                id=str(uuid4()),
                asset_id=event.asset_id,
                timestamp=event.timestamp,
                event_type="reasoning_started",
                title="Reasoning started",
                description=f"Reasoning run {event.run_id} began for the asset.",
                metadata={"run_id": event.run_id},
            )
        )

    def on_reasoning_completed(self, event: ReasoningCompleted) -> None:
        self._record(
            TimelineEvent(
                id=str(uuid4()),
                asset_id=event.asset_id,
                timestamp=event.timestamp,
                event_type="reasoning_completed",
                title="Reasoning completed",
                description=f"Reasoning run {event.run_id} finished for the asset.",
                metadata={"run_id": event.run_id},
            )
        )

    def on_recommendation_updated(self, event: RecommendationUpdated) -> None:
        previous = event.previous_recommendation or "none"
        self._record(
            TimelineEvent(
                id=str(uuid4()),
                asset_id=event.asset_id,
                timestamp=event.timestamp,
                event_type="recommendation_updated",
                title="Recommendation updated",
                description=(
                    f"Recommendation changed from {previous!r} to "
                    f"{event.new_recommendation!r}."
                ),
                metadata={
                    "run_id": event.run_id,
                    "previous_recommendation": event.previous_recommendation,
                    "new_recommendation": event.new_recommendation,
                },
            )
        )

    def on_trend_changed(self, event: TrendChanged) -> None:
        self._record(
            TimelineEvent(
                id=str(uuid4()),
                asset_id=event.asset_id,
                timestamp=event.timestamp,
                event_type="trend_changed",
                title="Trend changed",
                description=(
                    f"Trend changed from {event.previous_direction!r} to "
                    f"{event.new_direction!r}."
                ),
                metadata={
                    "run_id": event.run_id,
                    "previous_direction": event.previous_direction,
                    "new_direction": event.new_direction,
                    "stability_score": event.stability_score,
                    "volatility_score": event.volatility_score,
                },
            )
        )

    def _record(self, event: TimelineEvent) -> None:
        with self._unit_of_work_factory() as uow:
            repository = SqlAlchemyTimelineRepository(uow.session)
            repository.save(event)
            uow.commit()

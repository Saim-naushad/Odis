"""SQLAlchemy-backed timeline event repository."""

from sqlalchemy import select

from backend.app.domain.repositories.timeline_repository import TimelineRepository
from backend.app.domain.timeline import TimelineEvent
from backend.app.infrastructure.database.mappers.timeline_event import (
    timeline_event_to_domain,
    timeline_event_to_model,
)
from backend.app.infrastructure.database.models.timeline_event import TimelineEventModel
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository

_EVENT_TYPE_ORDER: dict[str, int] = {
    "observation_received": 0,
    "reasoning_started": 1,
    "recommendation_updated": 2,
    "reasoning_completed": 3,
}


class SqlAlchemyTimelineRepository(SqlAlchemyRepository, TimelineRepository):
    """Persist timeline events in PostgreSQL through SQLAlchemy."""

    def save(self, event: TimelineEvent) -> None:
        if self._session.get(TimelineEventModel, event.id) is not None:
            raise ValueError(f"timeline event with id {event.id!r} already exists")

        model = timeline_event_to_model(event)
        self._session.add(model)
        self._session.flush()

    def list_by_asset(self, asset_id: str) -> list[TimelineEvent]:
        statement = (
            select(TimelineEventModel)
            .where(TimelineEventModel.asset_id == asset_id)
            .order_by(
                TimelineEventModel.timestamp,
                TimelineEventModel.id,
            )
        )
        models = self._session.scalars(statement).all()
        events = [timeline_event_to_domain(model) for model in models]
        return sorted(
            events,
            key=lambda event: (
                event.timestamp,
                _EVENT_TYPE_ORDER.get(event.event_type, 99),
                event.id,
            ),
        )

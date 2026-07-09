"""Timeline persistence and recording specifications."""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from backend.app.application.events.domain_events import (
    ObservationCreated,
    ReasoningCompleted,
    ReasoningStarted,
    RecommendationUpdated,
    TrendChanged,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.events.handlers.timeline_event_handler import (
    TimelineEventHandler,
)
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.domain.timeline import TimelineEvent
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.repositories.timeline_repository import (
    SqlAlchemyTimelineRepository,
)


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://")


@pytest.fixture
def session_factory(
    sqlite_settings: Settings,
) -> Generator[Callable[[], Session], None, None]:
    engine = create_db_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        engine.dispose()


def _sample_event(
    *,
    event_id: str,
    asset_id: str = "asset-1",
    timestamp: datetime,
    event_type: str = "observation_received",
) -> TimelineEvent:
    return TimelineEvent(
        id=event_id,
        asset_id=asset_id,
        timestamp=timestamp,
        event_type=event_type,  # type: ignore[arg-type]
        title="Test event",
        description="Test description",
        metadata={"key": "value"},
    )


def test_timeline_repository_persists_and_lists_by_asset(
    session_factory: Callable[[], Session],
) -> None:
    first_ts = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    second_ts = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyTimelineRepository(uow.session)
        repository.save(
            _sample_event(
                event_id="event-1",
                timestamp=first_ts,
                event_type="observation_received",
            )
        )
        repository.save(
            _sample_event(
                event_id="event-2",
                timestamp=second_ts,
                event_type="reasoning_started",
            )
        )
        repository.save(
            _sample_event(
                event_id="event-other",
                asset_id="asset-2",
                timestamp=second_ts,
            )
        )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyTimelineRepository(uow.session)
        events = repository.list_by_asset("asset-1")

    assert [event.id for event in events] == ["event-1", "event-2"]
    assert events[0].event_type == "observation_received"
    assert events[1].event_type == "reasoning_started"


def test_timeline_repository_orders_oldest_to_newest(
    session_factory: Callable[[], Session],
) -> None:
    timestamps = [
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
    ]

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyTimelineRepository(uow.session)
        for index, timestamp in enumerate(timestamps):
            repository.save(
                _sample_event(
                    event_id=f"event-{index}",
                    timestamp=timestamp,
                )
            )
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        events = SqlAlchemyTimelineRepository(uow.session).list_by_asset("asset-1")

    assert [event.id for event in events] == ["event-1", "event-2", "event-0"]


def test_timeline_handler_records_domain_events(
    session_factory: Callable[[], Session],
) -> None:
    bus = DomainEventBus()
    handler = TimelineEventHandler(lambda: SqlAlchemyUnitOfWork(session_factory))
    bus.subscribe(ObservationCreated, handler.on_observation_created)
    bus.subscribe(ReasoningStarted, handler.on_reasoning_started)
    bus.subscribe(ReasoningCompleted, handler.on_reasoning_completed)
    bus.subscribe(RecommendationUpdated, handler.on_recommendation_updated)
    bus.subscribe(TrendChanged, handler.on_trend_changed)

    created_at = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
    started_at = datetime(2026, 1, 1, 9, 5, tzinfo=UTC)
    completed_at = datetime(2026, 1, 1, 9, 6, tzinfo=UTC)
    updated_at = datetime(2026, 1, 1, 9, 6, tzinfo=UTC)
    trend_at = datetime(2026, 1, 1, 9, 6, tzinfo=UTC)

    bus.publish(
        ObservationCreated(
            asset_id="asset-1",
            observation_id="obs-1",
            timestamp=created_at,
        )
    )
    bus.publish(
        ReasoningStarted(
            asset_id="asset-1",
            run_id="run-1",
            timestamp=started_at,
        )
    )
    bus.publish(
        RecommendationUpdated(
            asset_id="asset-1",
            run_id="run-1",
            previous_recommendation="Monitor",
            new_recommendation="Investigate",
            timestamp=updated_at,
        )
    )
    bus.publish(
        ReasoningCompleted(
            asset_id="asset-1",
            run_id="run-1",
            timestamp=completed_at,
        )
    )
    bus.publish(
        TrendChanged(
            asset_id="asset-1",
            run_id="run-1",
            previous_direction="stable",
            new_direction="rising",
            stability_score=80,
            volatility_score=15,
            timestamp=trend_at,
        )
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        events = SqlAlchemyTimelineRepository(uow.session).list_by_asset("asset-1")

    assert [event.event_type for event in events] == [
        "observation_received",
        "reasoning_started",
        "trend_changed",
        "recommendation_updated",
        "reasoning_completed",
    ]


def test_outbox_dispatch_records_timeline_events(
    session_factory: Callable[[], Session],
) -> None:
    from backend.app.domain.outbox import OutboxEvent

    bus = DomainEventBus()
    handler = TimelineEventHandler(lambda: SqlAlchemyUnitOfWork(session_factory))
    bus.subscribe(ObservationCreated, handler.on_observation_created)
    dispatcher = OutboxDispatcher(lambda: SqlAlchemyUnitOfWork(session_factory), bus)

    created_at = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            OutboxEvent(
                id=str(uuid4()),
                event_type="ObservationCreated",
                payload={
                    "asset_id": "asset-1",
                    "observation_id": "obs-1",
                    "timestamp": created_at.isoformat(),
                },
                created_at=created_at,
                dispatched_at=None,
            )
        )
        uow.commit()

    dispatcher.dispatch()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        events = SqlAlchemyTimelineRepository(uow.session).list_by_asset("asset-1")

    assert len(events) == 1
    assert events[0].event_type == "observation_received"
    assert events[0].metadata["observation_id"] == "obs-1"

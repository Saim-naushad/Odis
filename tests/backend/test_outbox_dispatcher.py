"""Outbox dispatcher specifications."""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.application.events.domain_events import ObservationCreated
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.domain.outbox import OutboxEvent
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


def test_undispatched_events_publish_and_mark_dispatched(
    session_factory: Callable[[], Session],
) -> None:
    bus = DomainEventBus()
    published: list[object] = []
    bus.subscribe(ObservationCreated, lambda event: published.append(event))
    dispatcher = OutboxDispatcher(lambda: SqlAlchemyUnitOfWork(session_factory), bus)

    created_at = datetime.now(UTC)
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

    assert len(published) == 1
    assert isinstance(published[0], ObservationCreated)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        row = uow.session.scalars(select(OutboxEvent)).one()
        assert row.dispatched_at is not None


def test_duplicate_dispatch_does_not_republish(
    session_factory: Callable[[], Session],
) -> None:
    bus = DomainEventBus()
    published: list[object] = []
    bus.subscribe(ObservationCreated, lambda event: published.append(event))
    dispatcher = OutboxDispatcher(lambda: SqlAlchemyUnitOfWork(session_factory), bus)

    created_at = datetime.now(UTC)
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
    dispatcher.dispatch()

    assert len(published) == 1


def test_unknown_events_are_safely_skipped(
    session_factory: Callable[[], Session],
) -> None:
    bus = DomainEventBus()
    dispatcher = OutboxDispatcher(lambda: SqlAlchemyUnitOfWork(session_factory), bus)

    created_at = datetime.now(UTC)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            OutboxEvent(
                id=str(uuid4()),
                event_type="UnknownEventType",
                payload={"foo": "bar"},
                created_at=created_at,
                dispatched_at=None,
            )
        )
        uow.commit()

    dispatcher.dispatch()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        row = uow.session.scalars(select(OutboxEvent)).one()
        assert row.dispatched_at is None


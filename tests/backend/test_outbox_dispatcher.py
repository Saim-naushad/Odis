"""Outbox dispatcher specifications."""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.application.events.domain_events import (
    AiFaultInvestigationUpdated,
    ObservationCreated,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.integration_events import IntegrationEvent
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.domain.outbox import OutboxEvent
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.metrics.outbox_metrics import outbox_pending_events
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)


class _CapturingIntegrationPublisher:
    def __init__(self) -> None:
        self.published: list[IntegrationEvent] = []

    def publish(self, event: IntegrationEvent) -> bool:
        self.published.append(event)
        return True


class _FailingIntegrationPublisher:
    def __init__(self) -> None:
        self.calls = 0

    def publish(self, event: IntegrationEvent) -> bool:
        self.calls += 1
        return False


class _FlakyIntegrationPublisher:
    """Fails the first `fail_times` calls, then succeeds."""

    def __init__(self, fail_times: int) -> None:
        self._fail_times = fail_times
        self.published: list[IntegrationEvent] = []

    def publish(self, event: IntegrationEvent) -> bool:
        if self._fail_times > 0:
            self._fail_times -= 1
            return False
        self.published.append(event)
        return True


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


def test_outbox_dispatcher_publishes_mapped_integration_events(
    session_factory: Callable[[], Session],
) -> None:
    bus = DomainEventBus()
    integration_publisher = _CapturingIntegrationPublisher()
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        bus,
        integration_publisher,
    )

    created_at = datetime.now(UTC)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            OutboxEvent(
                id=str(uuid4()),
                event_type="ReasoningCompleted",
                payload={
                    "asset_id": "asset-1",
                    "run_id": "run-1",
                    "timestamp": created_at.isoformat(),
                },
                created_at=created_at,
                dispatched_at=None,
            )
        )
        uow.commit()

    dispatcher.dispatch()

    assert len(integration_publisher.published) == 1
    assert integration_publisher.published[0].type == "DigitalTwinUpdated"


def test_outbox_dispatcher_skips_unmapped_integration_events(
    session_factory: Callable[[], Session],
) -> None:
    bus = DomainEventBus()
    integration_publisher = _CapturingIntegrationPublisher()
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        bus,
        integration_publisher,
    )

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

    assert integration_publisher.published == []


def test_ai_fault_investigation_updated_round_trips_through_the_outbox(
    session_factory: Callable[[], Session],
) -> None:
    """PR179: not mapped to any Kafka integration event by design — browser
    SSE delivery must not depend on live Kafka connectivity."""
    bus = DomainEventBus()
    published: list[AiFaultInvestigationUpdated] = []
    bus.subscribe(AiFaultInvestigationUpdated, published.append)
    integration_publisher = _CapturingIntegrationPublisher()
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        bus,
        integration_publisher,
    )

    created_at = datetime.now(UTC)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            OutboxEvent(
                id=str(uuid4()),
                event_type="AiFaultInvestigationUpdated",
                payload={
                    "asset_id": "asset-1",
                    "investigation_id": "inv-1",
                    "diagnosed_fault_class": "cooling_degradation",
                    "investigation_status": "OPEN",
                    "alert_transition_type": "confirmed",
                    "timestamp": created_at.isoformat(),
                },
                created_at=created_at,
                dispatched_at=None,
            )
        )
        uow.commit()

    dispatcher.dispatch()

    assert len(published) == 1
    assert published[0].asset_id == "asset-1"
    assert published[0].investigation_id == "inv-1"
    assert integration_publisher.published == []


def test_failed_kafka_publish_leaves_row_undispatched_for_retry(
    session_factory: Callable[[], Session],
) -> None:
    bus = DomainEventBus()
    integration_publisher = _FailingIntegrationPublisher()
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        bus,
        integration_publisher,
    )

    created_at = datetime.now(UTC)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            OutboxEvent(
                id=str(uuid4()),
                event_type="ReasoningCompleted",
                payload={
                    "asset_id": "asset-1",
                    "run_id": "run-1",
                    "timestamp": created_at.isoformat(),
                },
                created_at=created_at,
                dispatched_at=None,
            )
        )
        uow.commit()

    dispatcher.dispatch()

    assert integration_publisher.calls == 1
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        row = uow.session.scalars(select(OutboxEvent)).one()
        assert row.dispatched_at is None


def test_retry_dispatch_succeeds_after_transient_kafka_failure(
    session_factory: Callable[[], Session],
) -> None:
    bus = DomainEventBus()
    integration_publisher = _FlakyIntegrationPublisher(fail_times=1)
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        bus,
        integration_publisher,
    )

    created_at = datetime.now(UTC)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            OutboxEvent(
                id=str(uuid4()),
                event_type="ReasoningCompleted",
                payload={
                    "asset_id": "asset-1",
                    "run_id": "run-1",
                    "timestamp": created_at.isoformat(),
                },
                created_at=created_at,
                dispatched_at=None,
            )
        )
        uow.commit()

    dispatcher.dispatch()
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        row = uow.session.scalars(select(OutboxEvent)).one()
        assert row.dispatched_at is None
    assert integration_publisher.published == []

    dispatcher.dispatch()

    assert len(integration_publisher.published) == 1
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        row = uow.session.scalars(select(OutboxEvent)).one()
        assert row.dispatched_at is not None


def test_pending_gauge_reflects_undispatched_backlog(
    session_factory: Callable[[], Session],
) -> None:
    bus = DomainEventBus()
    integration_publisher = _FailingIntegrationPublisher()
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        bus,
        integration_publisher,
    )

    created_at = datetime.now(UTC)
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            OutboxEvent(
                id=str(uuid4()),
                event_type="ReasoningCompleted",
                payload={
                    "asset_id": "asset-1",
                    "run_id": "run-1",
                    "timestamp": created_at.isoformat(),
                },
                created_at=created_at,
                dispatched_at=None,
            )
        )
        uow.commit()

    dispatcher.dispatch()

    metric_family = next(iter(outbox_pending_events.collect()))
    assert metric_family.samples[0].value == 1.0


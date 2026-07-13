"""Investigation lifecycle domain, repository, service, and wiring specs."""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.application.events.domain_events import (
    InvestigationTransitionRecorded,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.events.handlers.timeline_event_handler import (
    TimelineEventHandler,
)
from backend.app.application.events.handlers.twin_cache_invalidation_handler import (
    DigitalTwinCacheInvalidationHandler,
)
from backend.app.application.investigation_service import (
    InvestigationService,
    InvestigationTransitionRejectedError,
)
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.domain.investigation import InvestigationEvent
from backend.app.domain.outbox import OutboxEvent
from backend.app.infrastructure.cache.memory_digital_twin_cache import (
    MemoryDigitalTwinCache,
)
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
from backend.app.infrastructure.repositories.investigation_repository import (
    SqlAlchemyInvestigationRepository,
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


def _transition(
    *,
    event_id: str,
    status: str = "ACKNOWLEDGED",
    recommendation_id: str = "rec-1",
    occurred_at: datetime,
) -> InvestigationEvent:
    return InvestigationEvent(
        id=event_id,
        asset_id="asset-1",
        recommendation_id=recommendation_id,
        status=status,  # type: ignore[arg-type]
        actor_id="op-1",
        actor_display_name="Operator One",
        occurred_at=occurred_at,
        notes=None,
    )


class TestInvestigationEventDomain:
    def test_rejects_empty_required_fields(self) -> None:
        with pytest.raises(ValueError, match="id must not be empty"):
            _transition(event_id="", occurred_at=datetime.now(UTC))

    def test_rejects_invalid_status(self) -> None:
        with pytest.raises(ValueError, match="status must be one of"):
            InvestigationEvent(
                id="inv-1",
                asset_id="asset-1",
                recommendation_id="rec-1",
                status="NEW",  # type: ignore[arg-type]
                actor_id="op-1",
                actor_display_name="Operator One",
                occurred_at=datetime.now(UTC),
            )


class TestInvestigationRepository:
    def test_persists_and_returns_latest_for_recommendation(
        self, session_factory: Callable[[], Session]
    ) -> None:
        first_ts = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        second_ts = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)

        with SqlAlchemyUnitOfWork(session_factory) as uow:
            repository = SqlAlchemyInvestigationRepository(uow.session)
            repository.save(
                _transition(
                    event_id="inv-1", status="ACKNOWLEDGED", occurred_at=first_ts
                )
            )
            repository.save(
                _transition(
                    event_id="inv-2", status="INVESTIGATING", occurred_at=second_ts
                )
            )
            repository.save(
                _transition(
                    event_id="inv-other",
                    recommendation_id="rec-2",
                    occurred_at=second_ts,
                )
            )
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory) as uow:
            repository = SqlAlchemyInvestigationRepository(uow.session)
            history = repository.list_for_recommendation("rec-1")
            latest = repository.get_latest_for_recommendation("rec-1")

        assert [event.id for event in history] == ["inv-1", "inv-2"]
        assert latest is not None
        assert latest.id == "inv-2"
        assert latest.status == "INVESTIGATING"

    def test_returns_none_when_no_transitions_recorded(
        self, session_factory: Callable[[], Session]
    ) -> None:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            repository = SqlAlchemyInvestigationRepository(uow.session)
            assert repository.get_latest_for_recommendation("missing") is None

    def test_rejects_duplicate_id(
        self, session_factory: Callable[[], Session]
    ) -> None:
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            repository = SqlAlchemyInvestigationRepository(uow.session)
            repository.save(
                _transition(event_id="inv-1", occurred_at=datetime.now(UTC))
            )
            uow.commit()

        with SqlAlchemyUnitOfWork(session_factory) as uow:
            repository = SqlAlchemyInvestigationRepository(uow.session)
            with pytest.raises(ValueError, match="already exists"):
                repository.save(
                    _transition(event_id="inv-1", occurred_at=datetime.now(UTC))
                )


class TestInvestigationService:
    def _service(
        self, session_factory: Callable[[], Session]
    ) -> tuple[InvestigationService, Callable[[], Session]]:
        uow = SqlAlchemyUnitOfWork(session_factory)
        repository = SqlAlchemyInvestigationRepository(uow.session)
        service = InvestigationService(uow, repository)
        return service, session_factory

    def test_records_first_transition_from_implicit_new(
        self, session_factory: Callable[[], Session]
    ) -> None:
        service, factory = self._service(session_factory)

        transition = service.record_transition(
            asset_id="asset-1",
            recommendation_id="rec-1",
            status="ACKNOWLEDGED",
            actor_id="op-1",
            actor_display_name="Operator One",
            notes="Paged on-call",
        )

        assert transition.status == "ACKNOWLEDGED"
        assert transition.notes == "Paged on-call"

        with SqlAlchemyUnitOfWork(factory) as uow:
            repository = SqlAlchemyInvestigationRepository(uow.session)
            latest = repository.get_latest_for_recommendation("rec-1")
        assert latest is not None
        assert latest.id == transition.id

    def test_allows_forward_transitions_including_skips(
        self, session_factory: Callable[[], Session]
    ) -> None:
        service, _ = self._service(session_factory)
        service.record_transition(
            asset_id="asset-1",
            recommendation_id="rec-1",
            status="ACKNOWLEDGED",
            actor_id="op-1",
            actor_display_name="Operator One",
        )

        # Skipping straight to RESOLVED from ACKNOWLEDGED is a legal forward move.
        resolved = service.record_transition(
            asset_id="asset-1",
            recommendation_id="rec-1",
            status="RESOLVED",
            actor_id="op-2",
            actor_display_name="Operator Two",
        )
        assert resolved.status == "RESOLVED"

    def test_rejects_backward_transition(
        self, session_factory: Callable[[], Session]
    ) -> None:
        service, _ = self._service(session_factory)
        service.record_transition(
            asset_id="asset-1",
            recommendation_id="rec-1",
            status="INVESTIGATING",
            actor_id="op-1",
            actor_display_name="Operator One",
        )

        with pytest.raises(InvestigationTransitionRejectedError):
            service.record_transition(
                asset_id="asset-1",
                recommendation_id="rec-1",
                status="ACKNOWLEDGED",
                actor_id="op-1",
                actor_display_name="Operator One",
            )

    def test_rejects_repeating_the_same_status(
        self, session_factory: Callable[[], Session]
    ) -> None:
        service, _ = self._service(session_factory)
        service.record_transition(
            asset_id="asset-1",
            recommendation_id="rec-1",
            status="ACKNOWLEDGED",
            actor_id="op-1",
            actor_display_name="Operator One",
        )

        with pytest.raises(InvestigationTransitionRejectedError):
            service.record_transition(
                asset_id="asset-1",
                recommendation_id="rec-1",
                status="ACKNOWLEDGED",
                actor_id="op-1",
                actor_display_name="Operator One",
            )

    def test_rejects_reopening_a_resolved_investigation(
        self, session_factory: Callable[[], Session]
    ) -> None:
        service, _ = self._service(session_factory)
        service.record_transition(
            asset_id="asset-1",
            recommendation_id="rec-1",
            status="RESOLVED",
            actor_id="op-1",
            actor_display_name="Operator One",
        )

        with pytest.raises(InvestigationTransitionRejectedError):
            service.record_transition(
                asset_id="asset-1",
                recommendation_id="rec-1",
                status="INVESTIGATING",
                actor_id="op-1",
                actor_display_name="Operator One",
            )

    def test_publishes_outbox_event_when_event_bus_configured(
        self, session_factory: Callable[[], Session]
    ) -> None:
        uow = SqlAlchemyUnitOfWork(session_factory)
        repository = SqlAlchemyInvestigationRepository(uow.session)
        bus = DomainEventBus()
        service = InvestigationService(uow, repository, event_bus=bus)

        service.record_transition(
            asset_id="asset-1",
            recommendation_id="rec-1",
            status="ACKNOWLEDGED",
            actor_id="op-1",
            actor_display_name="Operator One",
        )

        with SqlAlchemyUnitOfWork(session_factory) as check_uow:
            rows = list(
                check_uow.session.scalars(
                    select(OutboxEvent).where(
                        OutboxEvent.event_type == "InvestigationTransitionRecorded"
                    )
                )
            )
        assert len(rows) == 1
        assert rows[0].payload["recommendation_id"] == "rec-1"


class TestInvestigationEventWiring:
    """End-to-end: service -> outbox -> bus -> timeline + cache invalidation."""

    def test_outbox_dispatch_records_timeline_event_and_invalidates_cache(
        self, session_factory: Callable[[], Session]
    ) -> None:
        bus = DomainEventBus()
        timeline_handler = TimelineEventHandler(
            lambda: SqlAlchemyUnitOfWork(session_factory)
        )
        cache = MemoryDigitalTwinCache()
        cache_handler = DigitalTwinCacheInvalidationHandler(cache)
        bus.subscribe(
            InvestigationTransitionRecorded,
            timeline_handler.on_investigation_transition_recorded,
        )
        bus.subscribe(
            InvestigationTransitionRecorded,
            cache_handler.on_investigation_transition_recorded,
        )
        dispatcher = OutboxDispatcher(
            lambda: SqlAlchemyUnitOfWork(session_factory), bus
        )

        uow = SqlAlchemyUnitOfWork(session_factory)
        repository = SqlAlchemyInvestigationRepository(uow.session)
        service = InvestigationService(uow, repository, event_bus=bus)

        service.record_transition(
            asset_id="asset-1",
            recommendation_id="rec-1",
            status="ACKNOWLEDGED",
            actor_id="op-1",
            actor_display_name="Operator One",
            notes="Looking into it",
        )

        dispatcher.dispatch()

        from backend.app.infrastructure.repositories.timeline_repository import (
            SqlAlchemyTimelineRepository,
        )

        with SqlAlchemyUnitOfWork(session_factory) as check_uow:
            events = SqlAlchemyTimelineRepository(check_uow.session).list_by_asset(
                "asset-1"
            )

        assert len(events) == 1
        assert events[0].event_type == "investigation_transition"
        assert events[0].metadata["recommendation_id"] == "rec-1"
        assert events[0].metadata["notes"] == "Looking into it"

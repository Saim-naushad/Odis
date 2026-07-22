"""Shared application runtime bootstrap specifications."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from backend.app.application.bootstrap import (
    bootstrap_application_runtime,
    register_domain_event_handlers,
)
from backend.app.application.events.domain_events import (
    AiFaultInvestigationUpdated,
    HealthChanged,
    InvestigationTransitionRecorded,
    NotificationCreated,
    ObservationCreated,
    ReasoningCompleted,
    ReasoningStarted,
    RecommendationUpdated,
    RiskChanged,
    TrendChanged,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.events.handlers.monitoring_event_handler import (
    MonitoringEventHandler,
)
from backend.app.application.events.handlers.timeline_event_handler import (
    TimelineEventHandler,
)
from backend.app.application.monitoring_event_source import (
    InMemoryMonitoringEventSource,
)
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


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://", forecast_enabled=False)


@pytest.fixture
def db_session(sqlite_settings: Settings) -> Generator[Session, None, None]:
    engine = create_db_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def test_bootstrap_registers_all_domain_event_handlers(
    sqlite_settings: Settings,
    db_session: Session,
) -> None:
    runtime = bootstrap_application_runtime(
        sqlite_settings,
        unit_of_work_factory=lambda: SqlAlchemyUnitOfWork(lambda: db_session),
    )

    assert runtime.domain_event_bus is not None
    assert runtime.monitoring_event_source is not None
    assert runtime.digital_twin_cache is not None
    assert runtime.outbox_dispatcher is not None

    handlers = runtime.domain_event_bus._handlers
    assert HealthChanged in handlers
    assert RiskChanged in handlers
    assert RecommendationUpdated in handlers
    assert NotificationCreated in handlers
    assert ReasoningCompleted in handlers
    assert ObservationCreated in handlers
    assert ReasoningStarted in handlers
    assert TrendChanged in handlers
    assert InvestigationTransitionRecorded in handlers
    assert AiFaultInvestigationUpdated in handlers


def test_ai_fault_investigation_updated_only_reaches_the_monitoring_handler(
    sqlite_settings: Settings,
    db_session: Session,
) -> None:
    """PR179 regression guard: `ReasoningBridgeService` already writes
    timeline rows directly in its own uow — subscribing `TimelineEventHandler`
    to this event too would double-write them."""
    runtime = bootstrap_application_runtime(
        sqlite_settings,
        unit_of_work_factory=lambda: SqlAlchemyUnitOfWork(lambda: db_session),
    )

    subscribers = runtime.domain_event_bus._handlers[AiFaultInvestigationUpdated]
    bound_instances = [
        getattr(handler, "__self__", None) for handler in subscribers
    ]
    assert any(
        isinstance(instance, MonitoringEventHandler) for instance in bound_instances
    )
    assert not any(
        isinstance(instance, TimelineEventHandler) for instance in bound_instances
    )


def test_register_domain_event_handlers_without_database_skips_timeline(
    sqlite_settings: Settings,
) -> None:
    event_bus = DomainEventBus()
    monitoring_event_source = InMemoryMonitoringEventSource()
    digital_twin_cache = MemoryDigitalTwinCache()

    register_domain_event_handlers(
        event_bus,
        digital_twin_cache=digital_twin_cache,
        monitoring_event_source=monitoring_event_source,
        unit_of_work_factory=None,
    )

    handlers = event_bus._handlers
    assert ObservationCreated in handlers
    assert ReasoningCompleted in handlers
    assert HealthChanged in handlers
    assert ReasoningStarted not in handlers
    assert TrendChanged not in handlers

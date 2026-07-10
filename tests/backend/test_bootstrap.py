"""Shared application runtime bootstrap specifications."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from backend.app.application.bootstrap import (
    bootstrap_application_runtime,
    register_domain_event_handlers,
)
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

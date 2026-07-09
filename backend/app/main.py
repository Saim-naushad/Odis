"""FastAPI application entry point for the ODIS platform."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import Engine

from backend.app.api.middleware import HTTPMetricsMiddleware, RequestIDMiddleware
from backend.app.api.routers import (
    health_router,
    metrics_router,
    monitoring_router,
    observations_router,
    platform_router,
)
from backend.app.application.events.domain_events import (
    ObservationCreated,
    ReasoningCompleted,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.events.handlers.monitoring_event_handler import (
    MonitoringEventHandler,
)
from backend.app.application.monitoring_event_source import (
    InMemoryMonitoringEventSource,
)
from backend.app.application.reasoning_task_runner import ReasoningTaskRunner
from backend.app.infrastructure.config.settings import Settings, get_settings
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.logging import configure_logging, get_logger
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AppState:
    """Lightweight in-process application state."""

    started_at: datetime
    settings: Settings


def _build_lifespan(
    active_settings: Settings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Initialize and tear down lightweight application state."""
        engine: Engine | None = None
        app.state.engine = None
        app.state.session_factory = None
        app.state.reasoning_task_runner = None

        if active_settings.database_url is not None:
            engine = create_db_engine(active_settings)
            app.state.engine = engine
            session_factory = create_session_factory(engine)
            app.state.session_factory = session_factory

        app.state.runtime = AppState(
            started_at=datetime.now(UTC),
            settings=active_settings,
        )
        monitoring_event_source = InMemoryMonitoringEventSource()
        app.state.monitoring_event_source = monitoring_event_source
        domain_event_bus = DomainEventBus()
        app.state.domain_event_bus = domain_event_bus
        monitoring_handler = MonitoringEventHandler(monitoring_event_source)
        domain_event_bus.subscribe(
            ObservationCreated,
            monitoring_handler.on_observation_created,
        )
        domain_event_bus.subscribe(
            ReasoningCompleted,
            monitoring_handler.on_reasoning_completed,
        )
        if app.state.session_factory is not None:
            app.state.reasoning_task_runner = ReasoningTaskRunner(
                lambda: SqlAlchemyUnitOfWork(app.state.session_factory),
                domain_event_bus,
            )
        logger.info(
            "application_starting",
            app_name=active_settings.app_name,
            app_version=active_settings.app_version,
            environment=active_settings.environment,
        )
        yield
        if engine is not None:
            engine.dispose()
        logger.info(
            "application_shutdown",
            app_name=active_settings.app_name,
        )

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    active_settings = settings or get_settings()
    configure_logging(
        log_level=active_settings.log_level,
        environment=active_settings.environment,
    )

    app = FastAPI(
        title=active_settings.app_name,
        description=(
            "Industrial operational intelligence platform API. "
            "Provides the HTTP integration boundary for ODIS platform services."
        ),
        version=active_settings.app_version,
        lifespan=_build_lifespan(active_settings),
    )
    app.state.settings = active_settings
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(HTTPMetricsMiddleware)

    app.include_router(platform_router)
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(observations_router)
    app.include_router(monitoring_router)

    return app


app = create_app()

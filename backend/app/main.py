"""FastAPI application entry point for the ODIS platform."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy import Engine

from backend.app.api.routers import (
    health_router,
    monitoring_router,
    observations_router,
    platform_router,
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

logger = logging.getLogger(__name__)


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
        if app.state.session_factory is not None:
            app.state.reasoning_task_runner = ReasoningTaskRunner(
                app.state.session_factory,
                monitoring_event_source,
            )
        logger.info(
            "Starting %s v%s (%s)",
            active_settings.app_name,
            active_settings.app_version,
            active_settings.environment,
        )
        yield
        if engine is not None:
            engine.dispose()
        logger.info("Shutting down %s", active_settings.app_name)

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""
    active_settings = settings or get_settings()

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

    app.include_router(platform_router)
    app.include_router(health_router)
    app.include_router(observations_router)
    app.include_router(monitoring_router)

    return app


app = create_app()

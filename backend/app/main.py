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
from backend.app.application.bootstrap import bootstrap_application_runtime
from backend.app.infrastructure.config.settings import Settings, get_settings
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.logging import configure_logging, get_logger
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.tracing import (
    configure_tracing,
    instrument_fastapi_app,
    shutdown_tracing,
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
        app.state.outbox_dispatcher = None

        if active_settings.database_url is not None:
            engine = create_db_engine(active_settings)
            app.state.engine = engine
            session_factory = create_session_factory(engine)
            app.state.session_factory = session_factory

        app.state.runtime = AppState(
            started_at=datetime.now(UTC),
            settings=active_settings,
        )

        unit_of_work_factory = None
        if app.state.session_factory is not None:
            session_factory = app.state.session_factory

            def unit_of_work_factory() -> SqlAlchemyUnitOfWork:
                return SqlAlchemyUnitOfWork(session_factory)

        application_runtime = bootstrap_application_runtime(
            active_settings,
            unit_of_work_factory=unit_of_work_factory,
        )
        app.state.monitoring_event_source = application_runtime.monitoring_event_source
        app.state.digital_twin_cache = application_runtime.digital_twin_cache
        app.state.domain_event_bus = application_runtime.domain_event_bus
        app.state.outbox_dispatcher = application_runtime.outbox_dispatcher
        app.state.forecast_inference_engine = (
            application_runtime.forecast_inference_engine
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
        shutdown_tracing()
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
    configure_tracing(
        active_settings,
        service_name=active_settings.otel_service_name or "odis-api",
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
    instrument_fastapi_app(app, settings=active_settings)

    app.include_router(platform_router)
    app.include_router(health_router)
    app.include_router(metrics_router)
    app.include_router(observations_router)
    app.include_router(monitoring_router)

    return app


app = create_app()

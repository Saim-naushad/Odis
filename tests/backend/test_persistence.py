"""Persistence layer specifications for the ODIS platform backend."""

import contextlib

import pytest
from backend.app.api.dependencies.database import get_db_session
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.requests import Request


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://")


def _build_request(app: object) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "app": app,
    }
    return Request(scope)


def test_create_db_engine_requires_database_url() -> None:
    settings = Settings(database_url=None)

    with pytest.raises(ValueError, match="DATABASE_URL is not configured"):
        create_db_engine(settings)


def test_create_session_factory_returns_callable(sqlite_settings: Settings) -> None:
    engine = create_db_engine(sqlite_settings)
    session_factory = create_session_factory(engine)

    session = session_factory()
    try:
        assert isinstance(session, Session)
    finally:
        session.close()
        engine.dispose()


def test_get_db_session_yields_working_session(sqlite_settings: Settings) -> None:
    app = create_app(settings=sqlite_settings)

    with TestClient(app):
        request = _build_request(app)
        session_generator = get_db_session(request)
        session = next(session_generator)
        try:
            assert isinstance(session, Session)
            session.execute(text("SELECT 1"))
        finally:
            with contextlib.suppress(StopIteration):
                next(session_generator)


def test_get_db_session_raises_when_database_not_configured() -> None:
    app = create_app(settings=Settings(database_url=None))
    request = _build_request(app)

    with pytest.raises(RuntimeError, match="session factory is not configured"):
        next(get_db_session(request))


def test_app_lifespan_wires_database_state(sqlite_settings: Settings) -> None:
    app = create_app(settings=sqlite_settings)

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.engine is not None
        assert app.state.session_factory is not None


def test_app_without_database_url_skips_engine() -> None:
    app = create_app(settings=Settings(database_url=None))

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.engine is None
        assert app.state.session_factory is None


def test_declarative_base_metadata_includes_observations_table() -> None:
    from backend.app.infrastructure.database import models as _models  # noqa: F401

    assert "observations" in Base.metadata.tables

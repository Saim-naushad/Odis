"""Database engine and session factory configuration."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.tracing import instrument_sqlalchemy_engine


def _engine_connect_args(database_url: str) -> Mapping[str, Any]:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def create_db_engine(settings: Settings) -> Engine:
    """Create a SQLAlchemy engine from application settings."""
    if settings.database_url is None:
        msg = "DATABASE_URL is not configured"
        raise ValueError(msg)

    engine = create_engine(
        settings.database_url,
        connect_args=dict(_engine_connect_args(settings.database_url)),
        pool_pre_ping=not settings.database_url.startswith("sqlite"),
    )
    instrument_sqlalchemy_engine(engine, settings=settings)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine."""
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

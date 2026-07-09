"""Database session dependency for route handlers."""

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker

from backend.app.application.unit_of_work import UnitOfWork
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)


def get_db_session(request: Request) -> Generator[Session, None, None]:
    """Provide a request-scoped SQLAlchemy session to route handlers."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if not isinstance(session_factory, sessionmaker):
        msg = "Database session factory is not configured on the application"
        raise RuntimeError(msg)

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_unit_of_work(request: Request) -> Generator[UnitOfWork[Session], None, None]:
    """Provide a request-scoped UnitOfWork for application services."""
    session_factory = getattr(request.app.state, "session_factory", None)
    if not isinstance(session_factory, sessionmaker):
        msg = "Database session factory is not configured on the application"
        raise RuntimeError(msg)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        yield uow

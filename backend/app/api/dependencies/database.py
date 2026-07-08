"""Database session dependency for route handlers."""

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker


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

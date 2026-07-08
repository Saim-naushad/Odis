"""Base class for SQLAlchemy-backed repository implementations."""

from sqlalchemy.orm import Session


class SqlAlchemyRepository:
    """Shared foundation for platform repository implementations.

    Subclasses receive a request-scoped :class:`~sqlalchemy.orm.Session` and
    use it for all database operations. Domain repository interfaces define
    the persistence contract; this class provides the infrastructure pattern
    future implementations will follow.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """Return the active SQLAlchemy session for this repository."""
        return self._session

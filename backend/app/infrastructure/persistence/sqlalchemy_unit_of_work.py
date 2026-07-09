"""SQLAlchemy-backed Unit of Work implementation."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Final, Literal

from sqlalchemy.orm import Session

from backend.app.application.unit_of_work import UnitOfWork


class SqlAlchemyUnitOfWork(UnitOfWork[Session]):
    """Own a SQLAlchemy session and expose transaction operations."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory: Final[Callable[[], Session]] = session_factory
        self._session: Session = session_factory()
        self._completed = False

    @property
    def session(self) -> Session:
        return self._session

    def commit(self) -> None:
        self._session.commit()
        self._completed = True

    def rollback(self) -> None:
        self._session.rollback()
        self._completed = True

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        try:
            if exc_type is not None:
                if not self._completed:
                    self.rollback()
                return False
            if not self._completed:
                self.commit()
            return False
        finally:
            self.close()


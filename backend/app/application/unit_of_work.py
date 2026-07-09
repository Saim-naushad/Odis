"""Unit of Work abstraction for application services.

This lightweight protocol owns a persistence session lifecycle and defines
transaction boundaries via commit/rollback/close.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol, TypeVar

SessionT = TypeVar("SessionT")


class UnitOfWork(Protocol[SessionT], AbstractContextManager["UnitOfWork[SessionT]"]):
    """Define a minimal transaction boundary for application services."""

    @property
    def session(self) -> SessionT:
        """Return the active persistence session."""

    def commit(self) -> None:
        """Commit the active transaction."""

    def rollback(self) -> None:
        """Rollback the active transaction."""

    def close(self) -> None:
        """Release underlying resources."""


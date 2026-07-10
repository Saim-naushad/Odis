"""Application service for recording and reading worker heartbeats."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.repositories.worker_heartbeat_repository import (
    WorkerHeartbeatRepository,
)
from backend.app.domain.worker_heartbeat import WorkerHeartbeat
from backend.app.infrastructure.repositories.worker_heartbeat_repository import (
    SqlAlchemyWorkerHeartbeatRepository,
)


class WorkerHeartbeatService:
    """Record periodic worker heartbeats and read the freshest record."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork[Session]],
        *,
        worker_id: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._worker_id = worker_id
        self._now = now or (lambda: datetime.now(UTC))

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def record_heartbeat(self) -> None:
        """Persist the current worker heartbeat timestamp."""
        timestamp = self._now()
        with self._unit_of_work_factory() as uow:
            repository = self._repository(uow)
            repository.upsert(self._worker_id, timestamp)
            uow.commit()

    def get_most_recent(self) -> WorkerHeartbeat | None:
        """Return the freshest heartbeat without mutating state."""
        with self._unit_of_work_factory() as uow:
            return self._repository(uow).get_most_recent()

    @staticmethod
    def _repository(uow: UnitOfWork[Session]) -> WorkerHeartbeatRepository:
        return SqlAlchemyWorkerHeartbeatRepository(uow.session)

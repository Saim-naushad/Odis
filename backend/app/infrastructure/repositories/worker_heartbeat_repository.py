"""SQLAlchemy-backed worker heartbeat repository."""

from datetime import datetime

from sqlalchemy import select

from backend.app.domain.repositories.worker_heartbeat_repository import (
    WorkerHeartbeatRepository,
)
from backend.app.domain.worker_heartbeat import WorkerHeartbeat
from backend.app.infrastructure.database.models.worker_heartbeat import (
    WorkerHeartbeatModel,
)
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository


class SqlAlchemyWorkerHeartbeatRepository(
    SqlAlchemyRepository,
    WorkerHeartbeatRepository,
):
    """Persist worker heartbeats in PostgreSQL through SQLAlchemy."""

    def upsert(self, worker_id: str, last_seen_at: datetime) -> None:
        model = self._session.get(WorkerHeartbeatModel, worker_id)
        if model is None:
            self._session.add(
                WorkerHeartbeatModel(
                    worker_id=worker_id,
                    last_seen_at=last_seen_at,
                ),
            )
        else:
            model.last_seen_at = last_seen_at
        self._session.flush()

    def get_most_recent(self) -> WorkerHeartbeat | None:
        statement = (
            select(WorkerHeartbeatModel)
            .order_by(WorkerHeartbeatModel.last_seen_at.desc())
            .limit(1)
        )
        model = self._session.scalars(statement).first()
        if model is None:
            return None
        return WorkerHeartbeat(
            worker_id=model.worker_id,
            last_seen_at=model.last_seen_at,
        )

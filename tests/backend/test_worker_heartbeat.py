"""Worker heartbeat persistence specifications."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.app.application.worker_heartbeat_service import WorkerHeartbeatService
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)


class FixedClock:
    def __init__(self, current: datetime) -> None:
        self._current = current

    def now(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        self._current = self._current + timedelta(seconds=seconds)


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://")


@pytest.fixture
def session_factory(
    sqlite_settings: Settings,
) -> Generator[sessionmaker[Session], None, None]:
    engine = create_db_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


def test_worker_heartbeat_upserts_same_worker_id(
    session_factory: sessionmaker[Session],
) -> None:
    clock = FixedClock(datetime(2026, 7, 10, 12, 0, tzinfo=UTC))
    service = WorkerHeartbeatService(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        worker_id="worker-1",
        now=clock.now,
    )

    service.record_heartbeat()
    clock.advance(15)
    service.record_heartbeat()

    heartbeat = service.get_most_recent()
    assert heartbeat is not None
    assert heartbeat.worker_id == "worker-1"
    assert heartbeat.last_seen_at.replace(tzinfo=UTC) == clock.now()


def test_worker_heartbeat_returns_most_recent_across_workers(
    session_factory: sessionmaker[Session],
) -> None:
    clock = FixedClock(datetime(2026, 7, 10, 12, 0, tzinfo=UTC))
    older = WorkerHeartbeatService(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        worker_id="worker-old",
        now=clock.now,
    )
    newer = WorkerHeartbeatService(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        worker_id="worker-new",
        now=clock.now,
    )

    older.record_heartbeat()
    clock.advance(30)
    newer.record_heartbeat()

    heartbeat = newer.get_most_recent()
    assert heartbeat is not None
    assert heartbeat.worker_id == "worker-new"

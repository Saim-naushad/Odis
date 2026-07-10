"""Health endpoint specifications."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.application.health_service import HealthService
from backend.app.application.worker_heartbeat_service import WorkerHeartbeatService
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.main import create_app


class FixedClock:
    def __init__(self, current: datetime) -> None:
        self._current = current

    def now(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        self._current = self._current + timedelta(seconds=seconds)


@pytest.fixture
def sqlite_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "health_api.db"
    return Settings(database_url=f"sqlite:///{database_path}")


@pytest.fixture
def sqlite_client(sqlite_settings: Settings) -> Generator[TestClient, None, None]:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        yield client


def _record_worker_heartbeat(
    app: Any,
    *,
    worker_id: str = "test-worker-1",
    last_seen_at: datetime | None = None,
) -> None:
    session_factory = app.state.session_factory
    service = WorkerHeartbeatService(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        worker_id=worker_id,
        now=(lambda: last_seen_at) if last_seen_at is not None else None,
    )
    service.record_heartbeat()


def test_live_returns_alive_without_dependencies() -> None:
    app = create_app(settings=Settings(database_url=None))
    with TestClient(app) as client:
        response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_live_remains_alive_when_database_is_down(
    sqlite_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        engine = app.state.engine
        assert engine is not None
        Base.metadata.create_all(engine)

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("db down with secret password=abc")

        monkeypatch.setattr(engine, "connect", _boom)
        response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_ready_returns_ready_when_required_dependencies_are_healthy(
    sqlite_client: TestClient,
) -> None:
    _record_worker_heartbeat(sqlite_client.app)

    response = sqlite_client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["database"]["status"] == "healthy"
    assert payload["checks"]["database"]["required"] is True
    assert payload["checks"]["reasoning_job_queue"]["status"] == "healthy"
    assert payload["checks"]["worker"]["status"] == "healthy"


def test_ready_returns_503_when_no_worker_heartbeat_exists(
    sqlite_client: TestClient,
) -> None:
    response = sqlite_client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["worker"]["status"] == "unhealthy"
    assert payload["checks"]["worker"]["required"] is True
    assert "password" not in str(payload)


def test_ready_returns_503_when_worker_heartbeat_is_stale(
    sqlite_client: TestClient,
) -> None:
    stale_at = datetime.now(UTC) - timedelta(seconds=120)
    _record_worker_heartbeat(
        sqlite_client.app,
        last_seen_at=stale_at,
    )

    response = sqlite_client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["checks"]["worker"]["status"] == "unhealthy"
    assert payload["checks"]["worker"]["details"] is not None
    assert "password" not in payload["checks"]["worker"]["details"]


def test_ready_stays_200_when_redis_is_degraded(
    sqlite_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_worker_heartbeat(sqlite_client.app)
    monkeypatch.setattr(
        "backend.app.application.health_service.check_redis_connectivity",
        lambda *_args, **_kwargs: (False, None),
    )

    response = sqlite_client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["redis"]["status"] == "degraded"
    assert payload["checks"]["redis"]["required"] is False


def test_ready_stays_200_when_kafka_is_degraded(
    sqlite_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = sqlite_settings.model_copy(
        update={"kafka_bootstrap_servers": "kafka:9092"},
    )
    app = create_app(settings=settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        _record_worker_heartbeat(app)
        monkeypatch.setattr(
            "backend.app.application.health_service.check_kafka_connectivity",
            lambda *_args, **_kwargs: (False, None),
        )
        response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["checks"]["kafka"]["status"] == "degraded"
    assert payload["checks"]["kafka"]["required"] is False


def test_ready_returns_503_when_database_connectivity_fails(
    sqlite_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        engine = app.state.engine
        assert engine is not None
        Base.metadata.create_all(engine)
        _record_worker_heartbeat(app)

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("db down password=secret")

        monkeypatch.setattr(engine, "connect", _boom)
        response = client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"]["status"] == "unhealthy"
    assert "password" not in str(payload)


def test_ready_returns_503_when_reasoning_job_queue_is_unavailable(
    sqlite_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        _record_worker_heartbeat(app)

        def _boom(*_args: object, **_kwargs: object) -> int:
            raise RuntimeError("queue unavailable password=secret")

        monkeypatch.setattr(
            "backend.app.infrastructure.repositories.reasoning_job_repository.SqlAlchemyReasoningJobRepository.count_by_status",
            _boom,
        )
        response = client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["checks"]["reasoning_job_queue"]["status"] == "unhealthy"
    assert "password" not in str(payload)


def test_ready_returns_503_when_db_is_not_configured() -> None:
    app = create_app(settings=Settings(database_url=None))
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["engine"]["status"] == "unhealthy"
    assert payload["checks"]["session_factory"]["status"] == "unhealthy"


def test_health_payload_includes_required_and_optional_classifications(
    sqlite_client: TestClient,
) -> None:
    _record_worker_heartbeat(sqlite_client.app)

    response = sqlite_client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert isinstance(payload["uptime_seconds"], int)
    assert payload["checks"]["database"]["required"] is True
    assert payload["checks"]["worker"]["required"] is True
    assert payload["checks"]["redis"]["required"] is False
    assert payload["checks"]["kafka"]["required"] is False
    assert payload["checks"]["monitoring"]["required"] is False


def test_health_is_degraded_when_optional_dependency_fails(
    sqlite_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _record_worker_heartbeat(sqlite_client.app)
    monkeypatch.setattr(
        "backend.app.application.health_service.check_redis_connectivity",
        lambda *_args, **_kwargs: (False, None),
    )

    response = sqlite_client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["checks"]["database"]["status"] == "healthy"
    assert payload["checks"]["redis"]["status"] == "degraded"


def test_health_returns_unhealthy_when_database_is_unhealthy(
    sqlite_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        engine = app.state.engine
        assert engine is not None
        Base.metadata.create_all(engine)
        _record_worker_heartbeat(app)

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("db down password=secret")

        monkeypatch.setattr(engine, "connect", _boom)
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unhealthy"
    assert payload["checks"]["database"]["status"] == "unhealthy"
    assert "password" not in str(payload)


def test_worker_heartbeat_service_records_and_reads_most_recent(
    sqlite_settings: Settings,
) -> None:
    clock = FixedClock(datetime(2026, 7, 10, 12, 0, tzinfo=UTC))
    with TestClient(create_app(settings=sqlite_settings)) as client:
        app = cast(FastAPI, client.app)
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        session_factory = app.state.session_factory
        assert session_factory is not None

        service = WorkerHeartbeatService(
            lambda: SqlAlchemyUnitOfWork(session_factory),
            worker_id="worker-a",
            now=clock.now,
        )
        service.record_heartbeat()
        heartbeat = service.get_most_recent()

        assert heartbeat is not None
        assert heartbeat.worker_id == "worker-a"
        assert heartbeat.last_seen_at.replace(tzinfo=UTC) == clock.now()

        clock.advance(5)
        service.record_heartbeat()
        updated = service.get_most_recent()
        assert updated is not None
        assert updated.last_seen_at.replace(tzinfo=UTC) == clock.now()


def test_health_service_worker_check_uses_injected_clock(
    sqlite_settings: Settings,
) -> None:
    clock = FixedClock(datetime(2026, 7, 10, 12, 0, tzinfo=UTC))
    with TestClient(create_app(settings=sqlite_settings)) as client:
        app = cast(FastAPI, client.app)
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)

        service = WorkerHeartbeatService(
            lambda: SqlAlchemyUnitOfWork(app.state.session_factory),
            worker_id="worker-a",
            now=clock.now,
        )
        service.record_heartbeat()

        health_service = HealthService(
            settings=sqlite_settings,
            started_at=clock.now(),
            reasoning_engine_version="test",
            engine=app.state.engine,
            session_factory=app.state.session_factory,
            monitoring_event_source=MagicMock(),
            now=clock.now,
        )
        clock.advance(10)
        status_code, result = health_service.ready()

        assert status_code == 200
        assert result.checks["worker"].status == "healthy"

        clock.advance(25)
        status_code, result = health_service.ready()
        assert status_code == 503
        assert result.checks["worker"].status == "unhealthy"

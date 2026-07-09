"""Health endpoint specifications."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


@pytest.fixture
def sqlite_settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "health_api.db"
    return Settings(database_url=f"sqlite:///{database_path}")


@pytest.fixture
def sqlite_client(sqlite_settings: Settings) -> Generator[TestClient, None, None]:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        yield client


def test_live_returns_alive() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_ready_returns_ready_when_db_is_available(sqlite_client: TestClient) -> None:
    response = sqlite_client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["engine"] == "available"
    assert payload["checks"]["session_factory"] == "available"
    assert payload["checks"]["database"] == "healthy"


def test_ready_returns_503_when_db_is_not_configured() -> None:
    app = create_app(settings=Settings(database_url=None))
    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["engine"] == "missing"
    assert payload["checks"]["session_factory"] == "missing"
    assert payload["checks"]["database"] == "failed"


def test_ready_returns_503_when_database_connectivity_fails(
    sqlite_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        engine = getattr(app.state, "engine", None)
        assert engine is not None

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("db down")

        monkeypatch.setattr(engine, "connect", _boom)

        response = client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"] == "failed"


def test_health_payload_includes_uptime_and_metadata(sqlite_client: TestClient) -> None:
    response = sqlite_client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "healthy"
    assert isinstance(payload["uptime_seconds"], int)
    assert payload["uptime_seconds"] >= 0
    assert "version" in payload
    assert "environment" in payload
    assert "reasoning_engine" in payload
    assert payload["checks"]["database"] == "healthy"
    assert payload["checks"]["monitoring"] == "healthy"


def test_health_returns_503_when_database_is_unhealthy(
    sqlite_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app(settings=sqlite_settings)
    with TestClient(app) as client:
        engine = getattr(app.state, "engine", None)
        assert engine is not None

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("db down")

        monkeypatch.setattr(engine, "connect", _boom)

        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unhealthy"
    assert payload["checks"]["database"] == "unhealthy"

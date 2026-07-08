"""Platform metadata endpoint specifications."""

from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_root_returns_platform_metadata() -> None:
    settings = Settings(app_name="ODIS Test Platform", app_version="0.1.0")
    client = TestClient(create_app(settings=settings))

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "platform_name": "ODIS Test Platform",
        "reasoning_engine_version": "v1",
        "platform_phase": "phase-2",
    }


def test_openapi_metadata_uses_settings() -> None:
    settings = Settings(
        app_name="ODIS Platform",
        app_version="0.1.0",
        environment="test",
    )
    client = TestClient(create_app(settings=settings))

    response = client.get("/openapi.json")

    assert response.status_code == 200
    openapi = response.json()
    assert openapi["info"]["title"] == "ODIS Platform"
    assert openapi["info"]["version"] == "0.1.0"

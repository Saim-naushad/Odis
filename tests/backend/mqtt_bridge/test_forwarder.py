"""HTTP observation forwarder specifications."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.application.mqtt_bridge.forwarder import (
    ForwardOutcome,
    HttpObservationIngestionForwarder,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.main import create_app
from tests.builders import build_observation


class _ApiClientAdapter:
    def __init__(self, api_client: TestClient) -> None:
        self._api_client = api_client

    def post(self, path: str, *, json: dict[str, object]) -> httpx.Response:
        response = self._api_client.post(path, json=json)
        return httpx.Response(
            status_code=response.status_code,
            request=httpx.Request("POST", path),
        )

    def close(self) -> None:
        return None


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'mqtt-forwarder.db'}")
    app = create_app(settings=settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        yield client


def test_forwarder_returns_accepted_after_202(api_client: TestClient) -> None:
    observation = build_observation(
        id="mqtt-forward-1",
        asset_id="fuel-cell-stack-01",
        timestamp=datetime(2026, 7, 10, 12, 0, tzinfo=UTC),
    )

    with HttpObservationIngestionForwarder(
        "http://testserver",
        client=_ApiClientAdapter(api_client),  # type: ignore[arg-type]
    ) as forwarder:
        outcome = forwarder.forward(observation)

    assert outcome is ForwardOutcome.ACCEPTED
    response = api_client.get("/observations/mqtt-forward-1")
    assert response.status_code == 200


def test_forwarder_returns_duplicate_after_409(api_client: TestClient) -> None:
    observation = build_observation(id="mqtt-dup-1")

    with HttpObservationIngestionForwarder(
        "http://testserver",
        client=_ApiClientAdapter(api_client),  # type: ignore[arg-type]
    ) as forwarder:
        assert forwarder.forward(observation) is ForwardOutcome.ACCEPTED
        assert forwarder.forward(observation) is ForwardOutcome.DUPLICATE


def test_forwarder_returns_retryable_on_5xx() -> None:
    observation = build_observation(id="mqtt-5xx-1")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="http://testserver", transport=transport)
    forwarder = HttpObservationIngestionForwarder("http://testserver", client=client)

    assert forwarder.forward(observation) is ForwardOutcome.RETRYABLE
    client.close()


def test_forwarder_returns_retryable_on_network_failure() -> None:
    observation = build_observation(id="mqtt-network-1")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="http://testserver", transport=transport)
    forwarder = HttpObservationIngestionForwarder("http://testserver", client=client)

    assert forwarder.forward(observation) is ForwardOutcome.RETRYABLE
    client.close()

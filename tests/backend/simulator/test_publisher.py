"""Observation publisher specifications."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.main import create_app
from backend.simulator.machine import FuelCellMachine
from backend.simulator.publisher import ObservationPublisher
from backend.simulator.telemetry import (
    observation_to_payload,
    observations_from_machine,
)


class _RecordingResponse:
    def raise_for_status(self) -> None:
        return None


class _RecordingHttpClient:
    def __init__(self, api_client: TestClient) -> None:
        self._api_client = api_client

    def post(self, path: str, *, json: dict[str, object]) -> _RecordingResponse:
        response = self._api_client.post(path, json=json)
        response.raise_for_status()
        return _RecordingResponse()

    def close(self) -> None:
        return None


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'publisher.db'}")
    app = create_app(settings=settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        yield client


def test_publisher_posts_observations_to_platform_api(
    api_client: TestClient,
) -> None:
    machine = FuelCellMachine.default(asset_id="fuel-cell-stack-01")
    machine.tick(1.0)
    observations = observations_from_machine(
        machine,
        timestamp=datetime(2026, 7, 15, 9, 0, tzinfo=UTC),
        id_prefix="pub-test-1",
    )

    with ObservationPublisher(
        "http://testserver",
        client=_RecordingHttpClient(api_client),  # type: ignore[arg-type]
    ) as publisher:
        publisher.publish(observations)

    response = api_client.get("/observations")
    assert response.status_code == 200
    persisted_ids = {item["id"] for item in response.json()}
    assert persisted_ids == {observation.id for observation in observations}


def test_observation_payload_round_trips_through_api(
    api_client: TestClient,
) -> None:
    machine = FuelCellMachine.default()
    observations = observations_from_machine(
        machine,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        id_prefix="payload-test",
    )
    payload = observation_to_payload(observations[0])

    response = api_client.post("/observations", json=payload)

    assert response.status_code == 202
    assert response.json()["id"] == observations[0].id

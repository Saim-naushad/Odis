"""Observation publisher specifications."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.main import create_app
from backend.simulator.machine import FuelCellMachine
from backend.simulator.publisher import ObservationPublisher
from backend.simulator.telemetry import (
    TelemetryContext,
    core_observations_from_machine,
    observation_to_payload,
)
from domain.entities.observation import Observation


class _RecordingResponse:
    def __init__(self, status_code: int, *, _raise: object = None) -> None:
        self.status_code = status_code
        self._raise = _raise

    def raise_for_status(self) -> None:
        if self._raise is not None:
            raise self._raise  # type: ignore[misc]


class _RecordingHttpClient:
    def __init__(self, api_client: TestClient) -> None:
        self._api_client = api_client

    def post(self, path: str, *, json: dict[str, object]) -> _RecordingResponse:
        response = self._api_client.post(path, json=json)
        error: Exception | None = None
        try:
            response.raise_for_status()
        except Exception as exc:
            error = exc
        return _RecordingResponse(response.status_code, _raise=error)

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
    observations = core_observations_from_machine(
        machine,
        timestamp=datetime(2026, 7, 15, 9, 0, tzinfo=UTC),
        context=TelemetryContext(run_id="pub-test-1"),
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
    observations = core_observations_from_machine(
        machine,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        context=TelemetryContext(run_id="payload-test"),
    )
    payload = observation_to_payload(observations[0])

    response = api_client.post("/observations", json=payload)

    assert response.status_code == 202
    assert response.json()["id"] == observations[0].id


class _StubResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "stub error",
                request=httpx.Request("POST", "http://test"),
                response=self,  # type: ignore[arg-type]
            )


class _ScriptedHttpClient:
    """Fake httpx.Client whose post() replays a scripted sequence of
    outcomes - either a status code or an exception to raise."""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.call_count = 0

    def post(self, path: str, *, json: dict[str, object]) -> _StubResponse:
        self.call_count += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, int)
        return _StubResponse(outcome)

    def close(self) -> None:
        return None


def _one_observation() -> list[Observation]:
    machine = FuelCellMachine.default(asset_id="fuel-cell-stack-01")
    observations = core_observations_from_machine(
        machine,
        timestamp=datetime(2026, 7, 15, 9, 0, tzinfo=UTC),
        context=TelemetryContext(run_id="retry-test"),
    )
    return list(observations[:1])


def test_publisher_treats_409_as_idempotent_success() -> None:
    """observation_id is deterministic, so a 409 means the platform already
    durably persisted this exact observation on an earlier attempt - not a
    real failure."""
    client = _ScriptedHttpClient([409])
    publisher = ObservationPublisher("http://testserver", client=client)  # type: ignore[arg-type]

    publisher.publish(_one_observation())  # must not raise

    assert client.call_count == 1


def test_publisher_retries_transient_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single dropped connection or read timeout must not crash the
    simulator - it previously did, restarting the whole demo scenario
    mid-run (docker's restart policy resets PlantAlphaFleet's run_id)."""
    monkeypatch.setattr(
        "backend.simulator.publishers.http_publisher.time.sleep", lambda _: None
    )
    client = _ScriptedHttpClient(
        [httpx.ReadTimeout("timed out"), httpx.ConnectError("refused"), 202]
    )
    publisher = ObservationPublisher(
        "http://testserver", client=client  # type: ignore[arg-type]
    )

    publisher.publish(_one_observation())  # must not raise

    assert client.call_count == 3


def test_publisher_raises_after_exhausting_retry_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persistent (not transient) failure must still crash loudly rather
    than silently drop telemetry - retries only absorb transient blips."""
    monkeypatch.setattr(
        "backend.simulator.publishers.http_publisher.time.sleep", lambda _: None
    )
    client = _ScriptedHttpClient([httpx.ReadTimeout("timed out")] * 10)
    publisher = ObservationPublisher(
        "http://testserver", client=client  # type: ignore[arg-type]
    )

    with pytest.raises(httpx.TransportError):
        publisher.publish(_one_observation())

    assert client.call_count == 4  # bounded, not unbounded retry


def test_publisher_raises_for_genuine_non_conflict_http_errors() -> None:
    """A real server-side failure (not a duplicate-id conflict) must still
    surface as an error, not be silently swallowed."""
    client = _ScriptedHttpClient([500])
    publisher = ObservationPublisher(
        "http://testserver", client=client  # type: ignore[arg-type]
    )

    with pytest.raises(httpx.HTTPStatusError):
        publisher.publish(_one_observation())

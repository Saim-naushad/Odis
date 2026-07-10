"""MQTT delivery acknowledgement specifications."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.application.mqtt_bridge.forwarder import (
    ForwardOutcome,
    HttpObservationIngestionForwarder,
)
from backend.app.application.mqtt_bridge.ingestion_service import MqttIngestionService
from backend.app.application.mqtt_bridge.message import (
    MqttDelivery,
    MqttIncomingMessage,
)
from backend.app.application.mqtt_bridge.subscriber import (
    MessageHandler,
    MqttSubscriber,
)
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.main import create_app


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


class _AckTrackingSubscriber(MqttSubscriber):
    def __init__(self) -> None:
        self._handler: MessageHandler | None = None
        self.acknowledged_message_ids: list[int] = []

    def connect(self) -> None:
        return None

    def subscribe(self, topic_filter: str, *, qos: int) -> None:
        return None

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    def disconnect(self) -> None:
        return None

    def loop_forever(self) -> None:
        return None

    def acknowledge(self, message_id: int, qos: int) -> None:
        self.acknowledged_message_ids.append(message_id)

    def deliver(
        self,
        *,
        message_id: int,
        topic: str,
        payload: bytes,
        qos: int = 1,
    ) -> None:
        assert self._handler is not None
        message = MqttIncomingMessage(
            topic=topic,
            payload=payload,
            qos=qos,
            retain=False,
            message_id=message_id,
        )
        delivery = MqttDelivery(
            message=message,
            _acknowledge=lambda: self.acknowledge(message_id, qos),
        )
        self._handler(delivery)


def _telemetry_payload(
    *,
    observation_id: str,
    value: float = 72.4,
) -> bytes:
    return json.dumps(
        {
            "id": observation_id,
            "value": value,
            "unit": "celsius",
            "timestamp": "2026-07-10T12:00:00+00:00",
        }
    ).encode()


@pytest.fixture
def api_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'mqtt-ack.db'}")
    app = create_app(settings=settings)
    with TestClient(app) as client:
        assert app.state.engine is not None
        Base.metadata.create_all(app.state.engine)
        yield client


def _service(
    api_client: TestClient,
    subscriber: _AckTrackingSubscriber,
) -> MqttIngestionService:
    forwarder = HttpObservationIngestionForwarder(
        "http://testserver",
        client=_ApiClientAdapter(api_client),  # type: ignore[arg-type]
    )
    return MqttIngestionService(
        subscriber,
        forwarder,
        topic_filter="odis/v1/+/+/telemetry/+",
        qos=1,
    )


def test_acknowledges_after_api_returns_202(api_client: TestClient) -> None:
    subscriber = _AckTrackingSubscriber()
    _service(api_client, subscriber)

    subscriber.deliver(
        message_id=101,
        topic="odis/v1/plant-a/fuel-cell-stack-01/telemetry/stack_temperature",
        payload=_telemetry_payload(observation_id="mqtt-ack-202"),
    )

    assert subscriber.acknowledged_message_ids == [101]
    response = api_client.get("/observations/mqtt-ack-202")
    assert response.status_code == 200


def test_acknowledges_after_duplicate_409(api_client: TestClient) -> None:
    subscriber = _AckTrackingSubscriber()
    _service(api_client, subscriber)
    topic = "odis/v1/plant-a/fuel-cell-stack-01/telemetry/stack_temperature"
    payload = _telemetry_payload(observation_id="mqtt-ack-409")

    subscriber.deliver(message_id=201, topic=topic, payload=payload)
    subscriber.deliver(message_id=202, topic=topic, payload=payload)

    assert subscriber.acknowledged_message_ids == [201, 202]


def test_does_not_acknowledge_after_5xx(api_client: TestClient) -> None:
    subscriber = _AckTrackingSubscriber()
    attempts = {"count": 0}

    class _RetryableForwarder:
        def forward(self, observation: object) -> ForwardOutcome:
            attempts["count"] += 1
            return ForwardOutcome.RETRYABLE

    MqttIngestionService(
        subscriber,
        _RetryableForwarder(),
        topic_filter="odis/v1/+/+/telemetry/+",
        qos=1,
    )

    subscriber.deliver(
        message_id=301,
        topic="odis/v1/plant-a/fuel-cell-stack-01/telemetry/stack_temperature",
        payload=_telemetry_payload(observation_id="mqtt-no-ack-5xx"),
    )

    assert subscriber.acknowledged_message_ids == []
    assert attempts["count"] == 1


def test_does_not_acknowledge_after_network_failure(api_client: TestClient) -> None:
    subscriber = _AckTrackingSubscriber()

    class _NetworkFailureForwarder:
        def forward(self, observation: object) -> ForwardOutcome:
            return ForwardOutcome.RETRYABLE

    MqttIngestionService(
        subscriber,
        _NetworkFailureForwarder(),
        topic_filter="odis/v1/+/+/telemetry/+",
        qos=1,
    )

    subscriber.deliver(
        message_id=401,
        topic="odis/v1/plant-a/fuel-cell-stack-01/telemetry/stack_temperature",
        payload=_telemetry_payload(observation_id="mqtt-no-ack-network"),
    )

    assert subscriber.acknowledged_message_ids == []


def test_redelivery_after_success_before_ack_is_idempotent(
    api_client: TestClient,
) -> None:
    subscriber = _AckTrackingSubscriber()
    _service(api_client, subscriber)
    topic = "odis/v1/plant-a/fuel-cell-stack-01/telemetry/stack_temperature"
    payload = _telemetry_payload(observation_id="mqtt-redelivery-1")

    subscriber.deliver(message_id=501, topic=topic, payload=payload)
    assert subscriber.acknowledged_message_ids == [501]

    subscriber.acknowledged_message_ids.clear()
    subscriber.deliver(message_id=502, topic=topic, payload=payload)

    assert subscriber.acknowledged_message_ids == [502]
    list_response = api_client.get("/observations")
    assert list_response.status_code == 200
    matching = [
        item for item in list_response.json() if item["id"] == "mqtt-redelivery-1"
    ]
    assert len(matching) == 1

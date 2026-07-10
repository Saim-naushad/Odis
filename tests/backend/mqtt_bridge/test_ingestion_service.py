"""MQTT ingestion service specifications."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.app.application.mqtt_bridge.forwarder import ForwardOutcome
from backend.app.application.mqtt_bridge.ingestion_service import MqttIngestionService
from backend.app.application.mqtt_bridge.message import (
    MqttDelivery,
    MqttIncomingMessage,
)
from backend.app.application.mqtt_bridge.subscriber import (
    MessageHandler,
    MqttSubscriber,
)
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType


class _FakeForwarder:
    def __init__(self) -> None:
        self.observations: list[Observation] = []
        self.outcome = ForwardOutcome.ACCEPTED

    def forward(self, observation: Observation) -> ForwardOutcome:
        self.observations.append(observation)
        return self.outcome


class _FakeSubscriber(MqttSubscriber):
    def __init__(self) -> None:
        self._handler: MessageHandler | None = None
        self.subscriptions: list[tuple[str, int]] = []
        self.acknowledged_message_ids: list[int] = []

    def connect(self) -> None:
        return None

    def subscribe(self, topic_filter: str, *, qos: int) -> None:
        self.subscriptions.append((topic_filter, qos))

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
        message: MqttIncomingMessage,
        *,
        message_id: int = 1,
    ) -> None:
        assert self._handler is not None
        delivery = MqttDelivery(
            message=message,
            _acknowledge=lambda: self.acknowledge(message_id, message.qos),
        )
        self._handler(delivery)


def test_ingestion_service_maps_and_forwards_valid_message() -> None:
    subscriber = _FakeSubscriber()
    forwarder = _FakeForwarder()
    service = MqttIngestionService(
        subscriber,
        forwarder,
        topic_filter="odis/v1/+/+/telemetry/+",
        qos=1,
    )
    service.run()
    assert subscriber.subscriptions == [("odis/v1/+/+/telemetry/+", 1)]

    payload = json.dumps(
        {
            "id": "mqtt-service-1",
            "value": 3.3,
            "unit": "V",
            "timestamp": "2026-07-10T12:00:00+00:00",
        }
    ).encode()
    subscriber.deliver(
        MqttIncomingMessage(
            topic="odis/v1/plant-a/fuel-cell-stack-01/telemetry/voltage",
            payload=payload,
            qos=1,
            retain=False,
            message_id=11,
        ),
        message_id=11,
    )

    assert len(forwarder.observations) == 1
    observation = forwarder.observations[0]
    assert observation.id == "mqtt-service-1"
    assert observation.asset_id == "fuel-cell-stack-01"
    assert observation.measurement_type == MeasurementType(name="voltage")
    assert observation.value == 3.3
    assert observation.timestamp == datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    assert subscriber.acknowledged_message_ids == [11]


def test_ingestion_service_acks_terminal_mapping_errors_without_forwarding() -> None:
    subscriber = _FakeSubscriber()
    forwarder = _FakeForwarder()
    service = MqttIngestionService(
        subscriber,
        forwarder,
        topic_filter="odis/v1/+/+/telemetry/+",
        qos=1,
    )
    subscriber.set_message_handler(service._handle_delivery)

    subscriber.deliver(
        MqttIncomingMessage(
            topic="invalid/topic",
            payload=b"{}",
            qos=1,
            retain=False,
            message_id=12,
        ),
        message_id=12,
    )

    assert forwarder.observations == []
    assert subscriber.acknowledged_message_ids == [12]

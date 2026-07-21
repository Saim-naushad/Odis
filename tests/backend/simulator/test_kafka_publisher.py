"""`KafkaObservationPublisher` specification (PR177 producer side)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.simulator.publishers.kafka_publisher import (
    DEFAULT_TOPIC,
    EVENT_VERSION,
    KafkaObservationPublisher,
)
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType


class _FakeFuture:
    def get(self, timeout: float | None = None) -> None:
        return None


class _FakeProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes]] = []

    def send(self, topic: str, *, key: bytes, value: bytes) -> _FakeFuture:
        self.sent.append((topic, key, value))
        return _FakeFuture()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def _observation(**overrides: object) -> Observation:
    defaults: dict[str, object] = {
        "id": "obs-1",
        "asset_id": "fuel-cell-stack-01",
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "measurement_type": MeasurementType(name="stack_temperature"),
        "value": 65.0,
        "unit": "celsius",
    }
    defaults.update(overrides)
    return Observation(**defaults)  # type: ignore[arg-type]


def test_publish_sends_one_message_per_observation() -> None:
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )
    observations = [
        _observation(id="obs-1", measurement_type=MeasurementType(name="current")),
        _observation(id="obs-2", measurement_type=MeasurementType(name="voltage")),
    ]

    publisher.publish(observations)

    assert len(producer.sent) == 2


def test_published_envelope_matches_input_contract() -> None:
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )
    observation = _observation()

    publisher.publish([observation])

    topic, key, value = producer.sent[0]
    assert topic == DEFAULT_TOPIC
    assert key == b"fuel-cell-stack-01"
    payload = json.loads(value)
    assert payload["event_version"] == EVENT_VERSION
    assert payload["asset_id"] == "fuel-cell-stack-01"
    assert payload["measurement_name"] == "stack_temperature"
    assert payload["value"] == 65.0
    assert payload["unit"] == "celsius"
    assert payload["source"] == "plant-alpha-simulator"
    assert "event_id" in payload


def test_publish_keys_by_asset_id_for_partition_affinity() -> None:
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )
    publisher.publish([_observation(asset_id="fuel-cell-stack-02")])

    _topic, key, _value = producer.sent[0]
    assert key == b"fuel-cell-stack-02"


def test_custom_topic_is_used() -> None:
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", topic="custom.topic.v1", producer=producer
    )
    publisher.publish([_observation()])

    topic, _key, _value = producer.sent[0]
    assert topic == "custom.topic.v1"

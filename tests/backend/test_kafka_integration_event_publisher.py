from __future__ import annotations

from datetime import UTC, datetime

from backend.app.application.integration_events import IntegrationEvent
from backend.app.infrastructure.events.kafka_integration_event_publisher import (
    KafkaIntegrationEventPublisher,
)


class _FakeFuture:
    def __init__(self, *, should_fail: bool = False) -> None:
        self._should_fail = should_fail

    def get(self, timeout: float | None = None) -> None:
        if self._should_fail:
            raise RuntimeError("send failed")


class _FakeProducer:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.sent: list[tuple[str, bytes, bytes]] = []

    def send(self, topic: str, *, key: bytes, value: bytes) -> _FakeFuture:
        if self.should_fail:
            raise RuntimeError("producer error")
        self.sent.append((topic, key, value))
        return _FakeFuture()


def test_publisher_successful_publish_does_not_raise() -> None:
    producer = _FakeProducer()
    publisher = KafkaIntegrationEventPublisher(
        bootstrap_servers="kafka:9092",
        producer=producer,
    )
    event = IntegrationEvent(
        id="evt-1",
        type="DigitalTwinUpdated",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        payload={"asset_id": "asset-1"},
    )

    result = publisher.publish(event)

    assert result is True
    assert len(producer.sent) == 1
    topic, key, value = producer.sent[0]
    assert topic == "integration-events"
    assert key == b"evt-1"
    assert b'"type":"DigitalTwinUpdated"' in value


def test_publisher_failure_is_swallowed_and_reported() -> None:
    publisher = KafkaIntegrationEventPublisher(
        bootstrap_servers="kafka:9092",
        producer=_FakeProducer(should_fail=True),
    )
    event = IntegrationEvent(
        id="evt-2",
        type="DigitalTwinUpdated",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        payload={"asset_id": "asset-1"},
    )

    result = publisher.publish(event)

    assert result is False


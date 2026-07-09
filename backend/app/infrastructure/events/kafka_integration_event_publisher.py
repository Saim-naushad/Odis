"""Kafka-backed IntegrationEventPublisher implementation."""

from __future__ import annotations

import json
from typing import Any

from backend.app.application.integration_event_publisher import (
    IntegrationEventPublisher,
)
from backend.app.application.integration_events import IntegrationEvent
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics.integration_event_metrics import (
    record_integration_event_published,
    record_integration_publish_failure,
)

logger = get_logger(__name__)


class KafkaIntegrationEventPublisher(IntegrationEventPublisher):
    """Publish integration events to Kafka.

    Failures are swallowed (logged + metrics) because Kafka is an integration
    boundary and must never fail requests.
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        topic: str = "integration-events",
        producer: Any | None = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._producer = producer

    def publish(self, event: IntegrationEvent) -> None:
        try:
            producer = self._get_producer()
            payload = _serialize_event(event)
            future = producer.send(
                self._topic,
                key=event.id.encode("utf-8"),
                value=payload.encode("utf-8"),
            )
            # Synchronous confirmation to count as "published".
            future.get(timeout=5)
            record_integration_event_published(event.type)
        except Exception:
            record_integration_publish_failure()
            logger.warning(
                "kafka_integration_event_publish_failed",
                integration_event_type=event.type,
                integration_event_id=event.id,
                topic=self._topic,
                bootstrap_servers=self._bootstrap_servers,
                exc_info=True,
            )

    def _get_producer(self) -> Any:
        if self._producer is not None:
            return self._producer
        # Lazily import so unit tests don't need kafka-python installed.
        from kafka import KafkaProducer

        self._producer = KafkaProducer(bootstrap_servers=self._bootstrap_servers)
        return self._producer


def _serialize_event(event: IntegrationEvent) -> str:
    data: dict[str, Any] = {
        "id": event.id,
        "type": event.type,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": event.payload,
    }
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


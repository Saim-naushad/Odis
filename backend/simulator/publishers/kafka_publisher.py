"""Kafka publisher for simulator observations (PR177).

Publishes one versioned `telemetry.observation.v1` JSON message per
`Observation` — the same per-measurement granularity the MQTT publisher
already uses (`mqtt_publisher.MqttObservationPublisher`) — to a single
Kafka topic, keyed by `asset_id` so all of one asset's telemetry lands on
one partition and is consumed in order.

Reuses `kafka-python` the same way
`backend.app.infrastructure.events.kafka_integration_event_publisher`
does (lazy import, so unit tests don't need the library installed) —
this is the only Kafka client abstraction in the codebase; this publisher
does not introduce a second one.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from backend.simulator.telemetry import observation_to_payload
from domain.entities.observation import Observation

DEFAULT_TOPIC = "odis.telemetry.observations.v1"
EVENT_VERSION = "v1"


class KafkaObservationPublisher:
    """Publish observations to Kafka using the `telemetry.observation.v1`
    envelope — one message per measurement, matching the MQTT publisher's
    per-measurement granularity so downstream assembly logic is uniform
    regardless of transport."""

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        topic: str = DEFAULT_TOPIC,
        source: str = "plant-alpha-simulator",
        producer: Any | None = None,
    ) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._source = source
        self._producer = producer

    def _get_producer(self) -> Any:
        if self._producer is not None:
            return self._producer
        # Lazily import so unit tests don't need kafka-python installed.
        from kafka import KafkaProducer

        self._producer = KafkaProducer(bootstrap_servers=self._bootstrap_servers)
        return self._producer

    def publish(self, observations: Sequence[Observation]) -> None:
        producer = self._get_producer()
        for observation in observations:
            payload = _envelope(observation, source=self._source)
            future = producer.send(
                self._topic,
                key=observation.asset_id.encode("utf-8"),
                value=json.dumps(
                    payload, separators=(",", ":"), sort_keys=True
                ).encode("utf-8"),
            )
            future.get(timeout=5)

    def close(self) -> None:
        if self._producer is not None:
            self._producer.flush()
            self._producer.close()

    def __enter__(self) -> KafkaObservationPublisher:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _envelope(observation: Observation, *, source: str) -> dict[str, Any]:
    payload = observation_to_payload(observation)
    return {
        "event_id": str(uuid4()),
        "event_version": EVENT_VERSION,
        "asset_id": observation.asset_id,
        "timestamp": payload["timestamp"],
        "measurement_name": observation.measurement_type.name,
        "value": observation.value,
        "unit": observation.unit,
        "source": source,
    }

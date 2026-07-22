"""Thin Kafka consumer/producer wrappers for the reasoning-bridge worker.

Uses `kafka-python` — the one Kafka client library already a dependency
of this codebase — with the same lazy-import style as
`backend.app.infrastructure.events.kafka_integration_event_publisher` and
`backend.simulator.inference_worker.kafka_io`. This is a small, local
reimplementation of that same thin wrapper shape rather than an import
from `backend.simulator.inference_worker` — `backend/app` and
`backend/simulator` intentionally have no dependency on each other in
either direction (confirmed during PR178's audit: `backend/simulator/
inference_worker/` has zero imports from `backend.app`, and nothing in
`backend/app` previously imported from `backend/simulator`); introducing
one just to share ~30 lines of generic client-wrapper code would be a
worse trade than the small duplication.

Delivery semantics mirror PR177's worker exactly: at-least-once
consumption (`enable_auto_commit=False`), offsets committed only after
the triggering message's required persistence/publish side effects
succeed, and deterministic downstream event identity for safe replay.
"""

from __future__ import annotations

import json
import time
from typing import Any

from backend.app.infrastructure.logging import get_logger

logger = get_logger(__name__)


def create_consumer(
    *,
    bootstrap_servers: str,
    topic: str,
    group_id: str,
) -> Any:
    # Lazily import so unit tests don't need kafka-python installed.
    from kafka import KafkaConsumer

    return KafkaConsumer(
        topic,
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )


def create_producer(*, bootstrap_servers: str) -> Any:
    # Lazily import so unit tests don't need kafka-python installed.
    from kafka import KafkaProducer

    return KafkaProducer(bootstrap_servers=bootstrap_servers)


def publish_with_retry(
    producer: Any,
    *,
    topic: str,
    key: str,
    value: dict[str, Any],
    max_retries: int,
    backoff_seconds: float,
) -> bool:
    """Publish one JSON message, retrying on failure. Returns whether it
    ultimately succeeded — callers must not commit the triggering
    consumer offset on failure."""
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    attempt = 0
    while True:
        try:
            future = producer.send(topic, key=key.encode("utf-8"), value=payload)
            future.get(timeout=5)
            return True
        except Exception:
            attempt += 1
            logger.warning(
                "reasoning_bridge_publish_attempt_failed",
                topic=topic,
                attempt=attempt,
                max_retries=max_retries,
                exc_info=True,
            )
            if attempt > max_retries:
                return False
            time.sleep(backoff_seconds * attempt)

"""Thin Kafka consumer/producer wrappers (PR177 spec sections 5 and 6).

Uses `kafka-python` — the one Kafka client library already a dependency
of this codebase (`backend.app.infrastructure.events.
kafka_integration_event_publisher`) — with the same lazy-import style so
unit tests never need the library installed. This is not a second Kafka
abstraction: it is the same client, wrapped only enough to give the
worker a `poll()`/manual-commit consumer loop, which nothing in the
codebase needed before this PR (no Kafka consumer existed).

Delivery semantics (spec section 6): **at-least-once consumption** —
`enable_auto_commit=False`; the worker commits offsets itself only after
a message's outcome (buffered, published, or rejected-and-reported) is
fully handled, never before. Combined with deterministic downstream
event identity (`identity.py`), a replayed message (duplicate delivery,
worker restart, offset replay) republishes the *same* `event_id` rather
than an uncontrolled duplicate.
"""

from __future__ import annotations

import json
import time
from typing import Any

from backend.simulator.inference_worker.logging_setup import get_logger

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
    consumer offset on failure (spec section 5: "offset commit occurs
    only after required publishes succeed")."""
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
                "fault_inference_publish_attempt_failed",
                topic=topic,
                attempt=attempt,
                max_retries=max_retries,
                exc_info=True,
            )
            if attempt > max_retries:
                return False
            time.sleep(backoff_seconds * attempt)

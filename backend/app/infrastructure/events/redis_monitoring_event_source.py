"""Redis Pub/Sub backed monitoring event source for cross-process SSE fan-out."""

from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from typing import Any

import redis

from backend.app.application.monitoring_event_source import MonitoringEvent
from backend.app.infrastructure.logging import get_logger

logger = get_logger(__name__)

DEFAULT_MONITORING_CHANNEL = "odis:monitoring:events"


class RedisMonitoringEventSource:
    """Transport monitoring events across processes via Redis Pub/Sub.

    Redis is used only as the inter-process transport. Connected SSE
    subscribers are still fanned out in-memory inside the consuming process:
    a single background listener thread receives channel messages and pushes
    them onto local asyncio queues via each subscriber's event loop.

    The listener thread starts lazily on the first ``subscribe()`` call, so
    publisher-only processes (the reasoning worker) never open a Pub/Sub
    connection they do not need.
    """

    def __init__(
        self,
        *,
        redis_url: str | None = None,
        channel: str = DEFAULT_MONITORING_CHANNEL,
        client: redis.Redis | None = None,
        reconnect_delay_seconds: float = 2.0,
    ) -> None:
        if client is None and redis_url is None:
            msg = "either redis_url or client must be provided"
            raise ValueError(msg)
        self._client = client or redis.Redis.from_url(redis_url or "")
        self._channel = channel
        self._reconnect_delay_seconds = reconnect_delay_seconds
        self._lock = threading.Lock()
        self._subscribers: dict[
            asyncio.Queue[MonitoringEvent], asyncio.AbstractEventLoop
        ] = {}
        self._listener_started = False
        self._stopped = False
        self._publisher_connected_logged = False

    # -- publishing (worker and API processes) ------------------------------

    def publish(self, event: MonitoringEvent) -> None:
        """Publish a monitoring event to the Redis channel.

        Redis failures are logged and swallowed: monitoring delivery must
        never break reasoning or ingestion.
        """
        payload = json.dumps(event.to_json_dict(), separators=(",", ":"))
        try:
            self._client.publish(self._channel, payload)
        except redis.exceptions.RedisError as exc:
            self._publisher_connected_logged = False
            logger.warning(
                "monitoring_event_publish_failed",
                channel=self._channel,
                event_type=event.type,
                error=str(exc),
            )
            return

        if not self._publisher_connected_logged:
            self._publisher_connected_logged = True
            logger.info(
                "redis_monitoring_publisher_connected",
                channel=self._channel,
            )
        logger.info(
            "monitoring_event_published",
            channel=self._channel,
            event_type=event.type,
            asset_id=event.asset_id,
            run_id=event.run_id,
        )

    # -- subscribing (API process, SSE handlers) ----------------------------

    def subscribe(self) -> asyncio.Queue[MonitoringEvent]:
        """Register a local SSE subscriber queue and ensure the listener runs.

        Must be called from a running event loop (the SSE route handler); the
        loop reference is captured so the listener thread can deliver events
        thread-safely.
        """
        queue: asyncio.Queue[MonitoringEvent] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers[queue] = loop
        self._ensure_listener()
        return queue

    def unsubscribe(self, queue: asyncio.Queue[MonitoringEvent]) -> None:
        with self._lock:
            self._subscribers.pop(queue, None)

    def close(self) -> None:
        """Stop the background listener (used by tests and shutdown paths)."""
        self._stopped = True

    # -- listener internals --------------------------------------------------

    def _ensure_listener(self) -> None:
        with self._lock:
            if self._listener_started:
                return
            self._listener_started = True
        thread = threading.Thread(
            target=self._listen_forever,
            name="redis-monitoring-subscriber",
            daemon=True,
        )
        thread.start()

    def _listen_forever(self) -> None:
        while not self._stopped:
            pubsub: redis.client.PubSub | None = None
            try:
                pubsub = self._client.pubsub(ignore_subscribe_messages=True)
                pubsub.subscribe(self._channel)
                logger.info(
                    "redis_monitoring_subscriber_connected",
                    channel=self._channel,
                )
                while not self._stopped:
                    message = pubsub.get_message(timeout=1.0)
                    if message is None:
                        continue
                    if message.get("type") != "message":
                        continue
                    event = _deserialize(message.get("data"))
                    if event is None:
                        continue
                    logger.info(
                        "monitoring_event_received",
                        channel=self._channel,
                        event_type=event.type,
                        asset_id=event.asset_id,
                        run_id=event.run_id,
                    )
                    self._fan_out(event)
            except redis.exceptions.RedisError as exc:
                logger.warning(
                    "redis_monitoring_reconnecting",
                    channel=self._channel,
                    error=str(exc),
                )
                time.sleep(self._reconnect_delay_seconds)
            finally:
                if pubsub is not None:
                    with contextlib.suppress(redis.exceptions.RedisError):
                        pubsub.close()

    def _fan_out(self, event: MonitoringEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers.items())
        for queue, loop in subscribers:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                # The subscriber's event loop has closed; drop the queue.
                with self._lock:
                    self._subscribers.pop(queue, None)


def _deserialize(raw: Any) -> MonitoringEvent | None:
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        obj = json.loads(raw)
        return MonitoringEvent.create(
            event_type=str(obj["type"]),
            asset_id=obj.get("asset_id"),
            run_id=obj.get("run_id"),
            timestamp=str(obj["timestamp"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "monitoring_event_deserialize_failed",
            error=str(exc),
        )
        return None

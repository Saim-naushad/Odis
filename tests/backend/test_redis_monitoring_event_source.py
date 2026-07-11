"""Tests for the Redis-backed cross-process monitoring event source."""

import asyncio
import json

import fakeredis

from backend.app.application.monitoring_event_source import MonitoringEvent
from backend.app.application.monitoring_sse_stream import stream_monitoring_sse_events
from backend.app.infrastructure.events.redis_monitoring_event_source import (
    RedisMonitoringEventSource,
)


def _make_pair() -> tuple[RedisMonitoringEventSource, RedisMonitoringEventSource]:
    """Two sources sharing one fake Redis server, simulating worker and API."""
    server = fakeredis.FakeServer()
    publisher = RedisMonitoringEventSource(
        client=fakeredis.FakeRedis(server=server),
        reconnect_delay_seconds=0.05,
    )
    subscriber = RedisMonitoringEventSource(
        client=fakeredis.FakeRedis(server=server),
        reconnect_delay_seconds=0.05,
    )
    return publisher, subscriber


async def _publish_until_received(
    publisher: RedisMonitoringEventSource,
    queue: asyncio.Queue[MonitoringEvent],
    event: MonitoringEvent,
    *,
    attempts: int = 50,
) -> MonitoringEvent:
    """Publish repeatedly until the subscriber thread delivers the event.

    The background listener subscribes asynchronously; early publishes may
    land before the channel subscription is registered.
    """
    for _ in range(attempts):
        publisher.publish(event)
        try:
            return await asyncio.wait_for(queue.get(), timeout=0.2)
        except TimeoutError:
            continue
    raise AssertionError("event was not delivered across instances")


def test_event_propagates_across_instances() -> None:
    """A worker-process publish reaches an API-process SSE subscriber queue."""
    publisher, subscriber = _make_pair()

    async def run() -> None:
        queue = subscriber.subscribe()
        sent = MonitoringEvent.create(
            event_type="run_updated",
            asset_id="fuel-cell-stack-01",
            run_id="run-42",
            timestamp="2026-07-11T06:00:00+00:00",
        )

        received = await _publish_until_received(publisher, queue, sent)

        assert received == sent

    try:
        asyncio.run(run())
    finally:
        publisher.close()
        subscriber.close()


def test_payload_format_is_preserved_over_the_wire() -> None:
    """The transported JSON matches MonitoringEvent.to_json_dict exactly."""
    server = fakeredis.FakeServer()
    raw_client = fakeredis.FakeRedis(server=server)
    publisher = RedisMonitoringEventSource(
        client=fakeredis.FakeRedis(server=server),
    )

    pubsub = raw_client.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe("odis:monitoring:events")
    # Drain the subscribe confirmation before publishing.
    pubsub.get_message(timeout=1.0)

    event = MonitoringEvent.create(
        event_type="asset_updated",
        asset_id="asset-1",
        run_id="run-1",
        timestamp="2026-01-01T00:00:00+00:00",
    )
    publisher.publish(event)

    message = pubsub.get_message(timeout=1.0)
    assert message is not None and message["type"] == "message"
    assert json.loads(message["data"]) == event.to_json_dict()
    publisher.close()


def test_optional_fields_survive_round_trip() -> None:
    """Events without asset_id/run_id deserialize back without extra fields."""
    publisher, subscriber = _make_pair()

    async def run() -> None:
        queue = subscriber.subscribe()
        sent = MonitoringEvent.create(
            event_type="platform_updated",
            timestamp="2026-01-01T00:00:00+00:00",
        )

        received = await _publish_until_received(publisher, queue, sent)

        assert received == sent
        assert received.asset_id is None
        assert received.run_id is None

    try:
        asyncio.run(run())
    finally:
        publisher.close()
        subscriber.close()


def test_unsubscribed_queue_stops_receiving() -> None:
    publisher, subscriber = _make_pair()

    async def run() -> None:
        active = subscriber.subscribe()
        dropped = subscriber.subscribe()
        subscriber.unsubscribe(dropped)

        sent = MonitoringEvent.create(event_type="asset_updated", asset_id="a-1")
        await _publish_until_received(publisher, active, sent)

        assert dropped.empty()

    try:
        asyncio.run(run())
    finally:
        publisher.close()
        subscriber.close()


def test_publish_survives_redis_failure() -> None:
    """Publishing without a reachable Redis logs and returns, never raises."""
    source = RedisMonitoringEventSource(
        redis_url="redis://localhost:1/0",  # nothing listening
    )

    source.publish(MonitoringEvent.create(event_type="asset_updated", asset_id="a-1"))
    source.close()


def test_sse_stream_emits_event_delivered_via_redis() -> None:
    """Full API-side chain: Redis message -> local queue -> encoded SSE frame."""
    publisher, subscriber = _make_pair()

    async def run() -> None:
        # Warm up: ensure the background Redis subscription is active before
        # relying on a single publish reaching the SSE stream.
        probe = subscriber.subscribe()
        await _publish_until_received(
            publisher, probe, MonitoringEvent.create(event_type="platform_updated")
        )
        subscriber.unsubscribe(probe)

        disconnected = False

        async def is_disconnected() -> bool:
            return disconnected

        stream = stream_monitoring_sse_events(
            is_disconnected=is_disconnected,
            event_source=subscriber,
            heartbeat_interval_s=5,
        )

        # First frame is the heartbeat emitted on connect.
        first = await asyncio.wait_for(anext(stream), timeout=10)
        assert "event: heartbeat" in first

        sent = MonitoringEvent.create(
            event_type="run_updated",
            asset_id="fuel-cell-stack-01",
            run_id="run-42",
            timestamp="2026-07-11T06:00:00+00:00",
        )
        publisher.publish(sent)

        frame: str | None = None
        for _ in range(5):
            candidate = await asyncio.wait_for(anext(stream), timeout=10)
            if "event: monitoring" in candidate:
                frame = candidate
                break
        assert frame is not None, "SSE monitoring frame was not emitted"
        payload = json.loads(frame.split("data: ", 1)[1].strip())
        assert payload == sent.to_json_dict()

        disconnected = True

    try:
        asyncio.run(run())
    finally:
        publisher.close()
        subscriber.close()

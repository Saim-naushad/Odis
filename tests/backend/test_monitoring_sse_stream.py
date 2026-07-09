"""Tests for monitoring SSE stream composition."""

import asyncio

from backend.app.application.monitoring_event_source import (
    InMemoryMonitoringEventSource,
    MonitoringEvent,
)
from backend.app.application.monitoring_sse_stream import stream_monitoring_sse_events


async def _collect_sse_messages(
    *,
    event_source: InMemoryMonitoringEventSource,
    max_messages: int,
    disconnect_after_messages: int | None = None,
) -> list[str]:
    messages: list[str] = []

    async def is_disconnected() -> bool:
        if disconnect_after_messages is None:
            return False
        return len(messages) >= disconnect_after_messages

    async for message in stream_monitoring_sse_events(
        is_disconnected=is_disconnected,
        event_source=event_source,
        heartbeat_interval_s=15,
    ):
        messages.append(message)
        if len(messages) >= max_messages:
            break

    return messages


def test_stream_emits_initial_heartbeat() -> None:
    source = InMemoryMonitoringEventSource()

    messages = asyncio.run(
        _collect_sse_messages(
            event_source=source,
            max_messages=1,
            disconnect_after_messages=1,
        )
    )

    assert messages[0].startswith("event: heartbeat\n")
    assert '"type": "heartbeat"' in messages[0]


def test_stream_forwards_published_monitoring_event() -> None:
    source = InMemoryMonitoringEventSource()

    async def run() -> list[str]:
        collected = asyncio.create_task(
            _collect_sse_messages(
                event_source=source,
                max_messages=2,
                disconnect_after_messages=2,
            )
        )
        await asyncio.sleep(0)
        source.publish(
            MonitoringEvent.create(
                event_type="asset_updated",
                asset_id="asset-a",
                run_id="run-1",
                timestamp="2026-01-01T12:00:00+00:00",
            )
        )
        return await collected

    messages = asyncio.run(run())

    assert messages[0].startswith("event: heartbeat\n")
    assert messages[1].startswith("event: monitoring\n")
    assert '"type": "asset_updated"' in messages[1]
    assert '"asset_id": "asset-a"' in messages[1]
    assert '"run_id": "run-1"' in messages[1]

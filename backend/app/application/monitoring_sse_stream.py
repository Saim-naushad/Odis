"""SSE stream composition for monitoring updates."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.app.application.monitoring_event_source import (
    MonitoringEvent,
    MonitoringEventSource,
)


@dataclass(frozen=True, slots=True)
class MonitoringStreamEvent:
    event: str
    data: str


def encode_sse(event: MonitoringStreamEvent) -> str:
    """Encode a single Server-Sent Event message."""
    lines = [f"event: {event.event}"]
    for data_line in event.data.splitlines() or [""]:
        lines.append(f"data: {data_line}")
    return "\n".join(lines) + "\n\n"


async def stream_monitoring_sse_events(
    *,
    is_disconnected: Callable[[], Awaitable[bool]],
    event_source: MonitoringEventSource,
    heartbeat_interval_s: int = 15,
) -> AsyncIterator[str]:
    """Yield encoded SSE messages for heartbeats and monitoring updates."""
    subscription = event_source.subscribe()

    async def next_monitoring_event(timeout: float) -> MonitoringEvent | None:
        try:
            return await asyncio.wait_for(subscription.get(), timeout=timeout)
        except TimeoutError:
            return None

    try:
        while True:
            if await is_disconnected():
                return

            heartbeat_payload = {
                "timestamp": datetime.now(UTC).isoformat(),
                "type": "heartbeat",
            }
            yield encode_sse(
                MonitoringStreamEvent(
                    event="heartbeat", data=json.dumps(heartbeat_payload)
                )
            )

            deadline = asyncio.get_running_loop().time() + heartbeat_interval_s
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break

                monitoring_event = await next_monitoring_event(remaining)
                if monitoring_event is None:
                    break

                yield encode_sse(
                    MonitoringStreamEvent(
                        event="monitoring",
                        data=json.dumps(monitoring_event.to_json_dict()),
                    )
                )
    finally:
        event_source.unsubscribe(subscription)

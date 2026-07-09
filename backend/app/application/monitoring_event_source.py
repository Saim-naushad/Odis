"""In-process monitoring event source for SSE fan-out."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class MonitoringEvent:
    """Forward-compatible monitoring SSE payload."""

    type: str
    timestamp: str
    asset_id: str | None = None
    run_id: str | None = None

    def to_json_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {
            "type": self.type,
            "timestamp": self.timestamp,
        }
        if self.asset_id is not None:
            payload["asset_id"] = self.asset_id
        if self.run_id is not None:
            payload["run_id"] = self.run_id
        return payload

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        asset_id: str | None = None,
        run_id: str | None = None,
        timestamp: str | None = None,
    ) -> MonitoringEvent:
        return cls(
            type=event_type,
            asset_id=asset_id,
            run_id=run_id,
            timestamp=timestamp or datetime.now(UTC).isoformat(),
        )


class MonitoringEventSource(Protocol):
    """Abstraction for publishing monitoring updates to SSE subscribers."""

    def publish(self, event: MonitoringEvent) -> None: ...

    def subscribe(self) -> asyncio.Queue[MonitoringEvent]: ...

    def unsubscribe(self, queue: asyncio.Queue[MonitoringEvent]) -> None: ...


class InMemoryMonitoringEventSource:
    """Fan-out monitoring events to active SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[MonitoringEvent]] = set()

    def publish(self, event: MonitoringEvent) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    def subscribe(self) -> asyncio.Queue[MonitoringEvent]:
        queue: asyncio.Queue[MonitoringEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[MonitoringEvent]) -> None:
        self._subscribers.discard(queue)

"""Tests for the in-process monitoring event source."""

import asyncio

from backend.app.application.monitoring_event_source import (
    InMemoryMonitoringEventSource,
    MonitoringEvent,
)


def test_publish_delivers_event_to_subscriber() -> None:
    async def run() -> None:
        source = InMemoryMonitoringEventSource()
        queue = source.subscribe()
        event = MonitoringEvent.create(
            event_type="asset_updated",
            asset_id="asset-1",
            run_id="run-1",
        )

        source.publish(event)

        received = await asyncio.wait_for(queue.get(), timeout=1)
        assert received == event

    asyncio.run(run())


def test_monitoring_event_to_json_dict_omits_optional_fields() -> None:
    event = MonitoringEvent.create(event_type="platform_updated")

    assert event.to_json_dict() == {
        "type": "platform_updated",
        "timestamp": event.timestamp,
    }


def test_monitoring_event_to_json_dict_includes_ids_when_present() -> None:
    event = MonitoringEvent.create(
        event_type="asset_updated",
        asset_id="asset-1",
        run_id="run-1",
        timestamp="2026-01-01T00:00:00+00:00",
    )

    assert event.to_json_dict() == {
        "type": "asset_updated",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "asset_id": "asset-1",
        "run_id": "run-1",
    }

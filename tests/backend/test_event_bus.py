from __future__ import annotations

from datetime import UTC, datetime

from backend.app.application.events.domain_events import (
    ObservationCreated,
    ReasoningCompleted,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.events.handlers.monitoring_event_handler import (
    MonitoringEventHandler,
)
from backend.app.application.monitoring_event_source import (
    InMemoryMonitoringEventSource,
)


def test_event_bus_executes_multiple_handlers_in_order() -> None:
    bus = DomainEventBus()
    calls: list[str] = []

    def first(_: ObservationCreated) -> None:
        calls.append("first")

    def second(_: ObservationCreated) -> None:
        calls.append("second")

    bus.subscribe(ObservationCreated, first)
    bus.subscribe(ObservationCreated, second)

    bus.publish(
        ObservationCreated(
            asset_id="asset-1",
            observation_id="obs-1",
            timestamp=datetime.now(UTC),
        )
    )

    assert calls == ["first", "second"]


def test_event_bus_ignores_unknown_event_types() -> None:
    bus = DomainEventBus()
    calls: list[str] = []

    def handler(_: ObservationCreated) -> None:
        calls.append("called")

    bus.subscribe(ObservationCreated, handler)

    class OtherEvent:
        pass

    bus.publish(OtherEvent())

    assert calls == []


def test_monitoring_event_handler_publishes_expected_events() -> None:
    source = InMemoryMonitoringEventSource()
    bus = DomainEventBus()
    handler = MonitoringEventHandler(source)
    bus.subscribe(ObservationCreated, handler.on_observation_created)
    bus.subscribe(ReasoningCompleted, handler.on_reasoning_completed)

    queue = source.subscribe()

    bus.publish(
        ObservationCreated(
            asset_id="asset-a",
            observation_id="obs-a",
            timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        )
    )
    created = queue.get_nowait()
    assert created.type == "asset_updated"
    assert created.asset_id == "asset-a"
    assert created.run_id is None

    bus.publish(
        ReasoningCompleted(
            asset_id="asset-a",
            run_id="run-1",
            timestamp=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
        )
    )
    run_event = queue.get_nowait()
    assert run_event.type == "run_updated"
    assert run_event.asset_id == "asset-a"
    assert run_event.run_id == "run-1"

    asset_event = queue.get_nowait()
    assert asset_event.type == "asset_updated"
    assert asset_event.asset_id == "asset-a"
    assert asset_event.run_id == "run-1"


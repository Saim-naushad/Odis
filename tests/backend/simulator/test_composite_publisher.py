"""`CompositeObservationPublisher` specification (PR178 correction:
single-source telemetry provenance).

Verifies that one already-constructed set of observations is fanned out
unchanged to every wrapped publisher — no recomputation, no re-ticking,
deterministic order, and a failure in one publisher does not trigger a
retry through the simulator's tick loop (the composite itself never
retries; it only fans out once)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from backend.simulator.publishers.composite_publisher import (
    CompositeObservationPublisher,
)
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType


class _FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.received: list[Sequence[Observation]] = []
        self.closed = False
        self._fail = fail

    def publish(self, observations: Sequence[Observation]) -> None:
        if self._fail:
            raise RuntimeError("publish failed")
        self.received.append(observations)

    def close(self) -> None:
        self.closed = True


def _observation(**overrides: object) -> Observation:
    defaults: dict[str, object] = {
        "id": "obs-1",
        "asset_id": "fuel-cell-stack-01",
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "measurement_type": MeasurementType(name="stack_temperature"),
        "value": 65.0,
        "unit": "celsius",
    }
    defaults.update(overrides)
    return Observation(**defaults)  # type: ignore[arg-type]


def test_requires_at_least_one_publisher() -> None:
    with pytest.raises(ValueError, match="at least one publisher"):
        CompositeObservationPublisher()


def test_fans_out_the_same_observations_to_every_publisher() -> None:
    first = _FakePublisher()
    second = _FakePublisher()
    composite = CompositeObservationPublisher(first, second)
    observations = [
        _observation(id="obs-1", measurement_type=MeasurementType(name="current")),
        _observation(id="obs-2", measurement_type=MeasurementType(name="voltage")),
    ]

    composite.publish(observations)

    assert first.received == [observations]
    assert second.received == [observations]


def test_publishes_the_identical_observation_instances_not_copies() -> None:
    """The whole point of the composite is that no publisher recomputes
    or reconstructs telemetry — every sub-publisher must see the exact
    same `Observation` objects (same ids, timestamps, values)."""
    first = _FakePublisher()
    second = _FakePublisher()
    composite = CompositeObservationPublisher(first, second)
    observation = _observation()

    composite.publish([observation])

    received_first = first.received[0][0]
    received_second = second.received[0][0]
    assert received_first is observation
    assert received_second is observation
    assert received_first.id == received_second.id
    assert received_first.timestamp == received_second.timestamp
    assert received_first.value == received_second.value


def test_publishes_in_fixed_constructor_order() -> None:
    order: list[str] = []

    class _OrderTrackingPublisher:
        def __init__(self, name: str) -> None:
            self._name = name

        def publish(self, observations: Sequence[Observation]) -> None:
            order.append(self._name)

        def close(self) -> None:
            pass

    composite = CompositeObservationPublisher(
        _OrderTrackingPublisher("kafka"), _OrderTrackingPublisher("http")
    )
    composite.publish([_observation()])

    assert order == ["kafka", "http"]


def test_one_publisher_failing_does_not_suppress_the_error_or_retry() -> None:
    """No distributed transaction, no silent swallow: a failing
    sub-publisher's exception propagates uncaught, and the composite
    itself performs no retry (a retry-by-re-ticking would have to happen,
    if at all, in the simulator's own loop, never inside this class)."""
    failing = _FakePublisher(fail=True)
    healthy = _FakePublisher()
    composite = CompositeObservationPublisher(failing, healthy)

    with pytest.raises(RuntimeError, match="publish failed"):
        composite.publish([_observation()])


def test_earlier_publisher_succeeding_is_not_rolled_back_on_later_failure() -> None:
    """Documents the non-atomic delivery semantics: if the first
    publisher (e.g. Kafka) succeeds and the second (e.g. HTTP) fails, the
    first publish is not undone."""
    healthy = _FakePublisher()
    failing = _FakePublisher(fail=True)
    composite = CompositeObservationPublisher(healthy, failing)
    observations = [_observation()]

    with pytest.raises(RuntimeError):
        composite.publish(observations)

    assert healthy.received == [observations]


def test_close_closes_every_wrapped_publisher() -> None:
    first = _FakePublisher()
    second = _FakePublisher()
    composite = CompositeObservationPublisher(first, second)

    composite.close()

    assert first.closed is True
    assert second.closed is True


def test_context_manager_closes_all_publishers() -> None:
    first = _FakePublisher()
    second = _FakePublisher()

    with CompositeObservationPublisher(first, second) as composite:
        composite.publish([_observation()])

    assert first.closed is True
    assert second.closed is True


def test_all_seven_inference_measurements_reach_both_publishers() -> None:
    """A single tick's full core+derived observation set (the same shape
    `_publish_kafka_snapshot` builds) must reach both sinks intact — no
    measurement silently dropped for one transport."""
    first = _FakePublisher()
    second = _FakePublisher()
    composite = CompositeObservationPublisher(first, second)
    measurement_names = (
        "stack_temperature",
        "coolant_flow",
        "fuel_flow",
        "voltage",
        "current",
        "coolant_inlet_temperature",
        "ambient_temperature",
    )
    observations = [
        _observation(id=f"obs-{name}", measurement_type=MeasurementType(name=name))
        for name in measurement_names
    ]

    composite.publish(observations)

    assert {obs.measurement_type.name for obs in first.received[0]} == set(
        measurement_names
    )
    assert {obs.measurement_type.name for obs in second.received[0]} == set(
        measurement_names
    )

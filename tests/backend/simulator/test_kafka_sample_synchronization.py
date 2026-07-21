"""Kafka snapshot synchronization specification (PR177 correction).

`_publish_kafka_snapshot` is the fix for a real gap the first PR177 smoke
test surfaced: the live simulator's existing dual-cadence core/derived
loop calls `datetime.now(UTC)` separately on independent cadences, so
core and derived observations for "the same moment" never share an exact
timestamp — and `TelemetrySample.from_observations` requires exactly
that. This module proves the fix: one tick, one timestamp, one complete,
assembleable sample, using the *real* `KafkaObservationPublisher` wire
format end to end (not a hand-built fixture).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from backend.simulator.__main__ import _publish_kafka_snapshot
from backend.simulator.dataset.features.config import DT_SECONDS
from backend.simulator.inference.telemetry import (
    CANONICAL_UNITS,
    REQUIRED_MEASUREMENTS,
)
from backend.simulator.inference_worker.assembly import AssemblyStatus, SampleAssembler
from backend.simulator.inference_worker.events import validate_telemetry_event
from backend.simulator.plant import PlantAlphaFleet
from backend.simulator.publishers.kafka_publisher import KafkaObservationPublisher
from backend.simulator.scenario_registry import build_scenario

_ASSET_ID = "fuel-cell-stack-01"


class _FakeFuture:
    def get(self, timeout: float | None = None) -> None:
        return None


class _FakeProducer:
    """Mirrors the fake producer in `test_kafka_integration_event_
    publisher.py`/`test_kafka_publisher.py` — captures exactly what would
    be sent to a real broker, so decoding it back proves real wire-format
    compatibility."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes, bytes]] = []

    def send(self, topic: str, *, key: bytes, value: bytes) -> _FakeFuture:
        self.sent.append((topic, key, value))
        return _FakeFuture()

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def _fleet() -> PlantAlphaFleet:
    return PlantAlphaFleet.create(run_id="sync-test", asset_ids=(_ASSET_ID,))


def _incrementing_clock(start: datetime, step_seconds: float) -> Callable[[], datetime]:
    state = {"t": start}

    def _now() -> datetime:
        state["t"] = state["t"] + timedelta(seconds=step_seconds)
        return state["t"]

    return _now


# --- Snapshot coherence -----------------------------------------------------


def test_all_seven_required_measurements_are_published_for_one_tick() -> None:
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )

    _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS)

    import json

    published_names = {
        json.loads(value)["measurement_name"] for _t, _k, value in producer.sent
    }
    assert set(REQUIRED_MEASUREMENTS).issubset(published_names)


def test_every_event_in_one_tick_shares_the_exact_same_timestamp() -> None:
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )

    returned_timestamp = _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS)

    import json

    timestamps = {json.loads(value)["timestamp"] for _t, _k, value in producer.sent}
    assert timestamps == {returned_timestamp.isoformat()}


def test_values_come_from_the_same_machine_state() -> None:
    """Core's `current`/`voltage` and derived's `power_output` must be
    mutually consistent (power = voltage * current / 1000) — proving
    both groups were built from one un-advanced-in-between machine
    state, not two separately-ticked ones."""
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )

    _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS)

    import json

    values = {
        json.loads(value)["measurement_name"]: json.loads(value)["value"]
        for _t, _k, value in producer.sent
    }
    expected_power_kw = round((values["voltage"] * values["current"]) / 1000.0, 4)
    assert values["power_output"] == expected_power_kw


def test_measurement_order_does_not_affect_assembly() -> None:
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )

    _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS)

    import json

    events = [
        validate_telemetry_event(json.loads(value)) for _t, _k, value in producer.sent
    ]
    assembler = SampleAssembler(
        timeout_seconds=30.0, max_buffered_timestamps_per_asset=8, max_tracked_assets=4
    )
    forward_outcomes = []
    for event in events:
        forward_outcomes.extend(assembler.ingest(event, now=0.0))

    reversed_assembler = SampleAssembler(
        timeout_seconds=30.0, max_buffered_timestamps_per_asset=8, max_tracked_assets=4
    )
    reversed_outcomes = []
    for event in reversed(events):
        reversed_outcomes.extend(reversed_assembler.ingest(event, now=0.0))

    assert forward_outcomes[-1].status is AssemblyStatus.COMPLETE
    assert reversed_outcomes[-1].status is AssemblyStatus.COMPLETE
    assert (
        forward_outcomes[-1].sample.values  # type: ignore[union-attr]
        == reversed_outcomes[-1].sample.values  # type: ignore[union-attr]
    )


def test_no_required_measurement_is_duplicated_or_omitted() -> None:
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )

    _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS)

    import json

    names = [json.loads(value)["measurement_name"] for _t, _k, value in producer.sent]
    required_names = [n for n in names if n in REQUIRED_MEASUREMENTS]
    assert sorted(required_names) == sorted(set(required_names))
    assert set(required_names) == set(REQUIRED_MEASUREMENTS)


def test_published_units_match_canonical_units() -> None:
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )

    _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS)

    import json

    for _t, _k, value in producer.sent:
        payload = json.loads(value)
        assert payload["unit"] == CANONICAL_UNITS[payload["measurement_name"]]


# --- Cadence -----------------------------------------------------------------


def test_simulated_time_advances_by_exactly_the_configured_interval() -> None:
    """The quantity the promoted runtime's features actually depend on:
    `FaultInferenceSession.ingest` derives `elapsed_sim_seconds` from
    sample *count* (`(n+1) * DT_SECONDS`), never from wall-clock
    timestamp gaps — so what must be exact is the simulated-time step
    per tick, not wall-clock spacing."""
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )

    for i in range(1, 6):
        _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS)
        assert fleet.elapsed_sim_seconds == pytest.approx(i * DT_SECONDS)


def test_successive_timestamps_are_strictly_monotonic_regardless_of_clock_jitter() -> (
    None
):
    """Wall-clock timestamps only need to strictly increase (required by
    `FaultInferenceSession.ingest`'s `NonMonotonicTimestampError` check);
    exact spacing is irrelevant to feature correctness. Uses an
    injectable clock so the test is deterministic and fast."""
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )
    clock = _incrementing_clock(datetime(2026, 1, 1, tzinfo=UTC), DT_SECONDS)

    timestamps = [
        _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS, now_fn=clock)
        for _ in range(5)
    ]

    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


def test_default_kafka_sample_interval_matches_trained_cadence() -> None:
    from backend.simulator.config import SimulatorSettings

    assert SimulatorSettings().kafka_sample_interval_seconds == DT_SECONDS


def test_wall_clock_publish_pacing_is_independent_of_simulated_cadence() -> None:
    """`kafka_publish_interval_seconds` (wall-clock pacing) can be sped up
    for demos/smoke tests without touching `kafka_sample_interval_seconds`
    (the simulated `dt_seconds` per tick feature correctness depends on)."""
    from backend.simulator.config import SimulatorSettings

    settings = SimulatorSettings(kafka_publish_interval_seconds=0.5)
    assert settings.kafka_publish_interval_seconds == 0.5
    assert settings.kafka_sample_interval_seconds == DT_SECONDS


# --- Real assembly (publisher -> SampleAssembler -> complete TelemetrySample) --


def test_real_publisher_output_assembles_into_a_complete_sample() -> None:
    fleet = _fleet()
    scenario = build_scenario("normal_operation")
    producer = _FakeProducer()
    publisher = KafkaObservationPublisher(
        bootstrap_servers="kafka:9092", producer=producer
    )
    clock = _incrementing_clock(datetime(2026, 1, 1, tzinfo=UTC), DT_SECONDS)

    _publish_kafka_snapshot(fleet, scenario, publisher, DT_SECONDS, now_fn=clock)

    import json

    raw_events = [json.loads(value) for _t, _k, value in producer.sent]
    events = [validate_telemetry_event(raw) for raw in raw_events]

    assembler = SampleAssembler(
        timeout_seconds=30.0, max_buffered_timestamps_per_asset=8, max_tracked_assets=4
    )
    outcomes = []
    for event in events:
        outcomes.extend(assembler.ingest(event, now=0.0))

    assert outcomes[-1].status is AssemblyStatus.COMPLETE
    sample = outcomes[-1].sample
    assert sample is not None
    assert sample.asset_id == _ASSET_ID
    assert set(sample.values) >= set(REQUIRED_MEASUREMENTS)

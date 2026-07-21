"""`SampleAssembler` specification (PR177 spec sections 4, 11, 17
"Assembly")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.simulator.inference.telemetry import REQUIRED_MEASUREMENTS
from backend.simulator.inference_worker.assembly import (
    REASON_CONFLICTING_DUPLICATE,
    REASON_INCOMPLETE_TIMEOUT,
    REASON_LATE,
    AssemblyStatus,
    SampleAssembler,
)

from .conftest import events_for_sample

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _assembler(**overrides: object) -> SampleAssembler:
    defaults: dict[str, object] = {
        "timeout_seconds": 30.0,
        "max_buffered_timestamps_per_asset": 8,
        "max_tracked_assets": 64,
    }
    defaults.update(overrides)
    return SampleAssembler(**defaults)  # type: ignore[arg-type]


def test_complete_sample_is_assembled_from_all_measurements() -> None:
    assembler = _assembler()
    events = events_for_sample(asset_id="a1", timestamp=_T0)

    outcomes = []
    for event in events[:-1]:
        outcomes.extend(assembler.ingest(event, now=0.0))
    assert all(o.status is AssemblyStatus.PENDING for o in outcomes)

    final_outcomes = assembler.ingest(events[-1], now=0.0)
    assert len(final_outcomes) == 1
    assert final_outcomes[0].status is AssemblyStatus.COMPLETE
    sample = final_outcomes[0].sample
    assert sample is not None
    assert sample.asset_id == "a1"
    assert set(sample.values) >= set(REQUIRED_MEASUREMENTS)


def test_out_of_order_measurement_arrival_within_same_timestamp_still_completes() -> (
    None
):
    assembler = _assembler()
    events = events_for_sample(asset_id="a1", timestamp=_T0)
    reversed_events = list(reversed(events))

    outcomes = []
    for event in reversed_events:
        outcomes.extend(assembler.ingest(event, now=0.0))
    assert outcomes[-1].status is AssemblyStatus.COMPLETE


def test_identical_duplicate_measurement_is_idempotently_ignored() -> None:
    assembler = _assembler()
    events = events_for_sample(asset_id="a1", timestamp=_T0)

    for event in events[:-1]:
        assembler.ingest(event, now=0.0)
    duplicate_outcomes = assembler.ingest(events[0], now=0.0)
    assert duplicate_outcomes[0].status is AssemblyStatus.PENDING

    final_outcomes = assembler.ingest(events[-1], now=0.0)
    assert final_outcomes[-1].status is AssemblyStatus.COMPLETE


def test_conflicting_duplicate_rejects_the_sample() -> None:
    assembler = _assembler()
    events = events_for_sample(asset_id="a1", timestamp=_T0)
    for event in events[:-1]:
        assembler.ingest(event, now=0.0)

    conflicting = events_for_sample(
        asset_id="a1",
        timestamp=_T0,
        measurements=(events[0].measurement_name,),
        values={events[0].measurement_name: events[0].value + 999.0},
    )[0]
    outcomes = assembler.ingest(conflicting, now=0.0)
    assert outcomes[0].status is AssemblyStatus.REJECTED
    assert outcomes[0].reason == REASON_CONFLICTING_DUPLICATE

    # Rejection drops the in-progress sample entirely — resending every
    # measurement builds a fresh one rather than resurrecting the old one.
    for event in events:
        outcomes = assembler.ingest(event, now=0.0)
    assert outcomes[-1].status is AssemblyStatus.COMPLETE


def test_incomplete_sample_expires_after_timeout() -> None:
    assembler = _assembler(timeout_seconds=10.0)
    events = events_for_sample(asset_id="a1", timestamp=_T0)
    for event in events[:-1]:
        assembler.ingest(event, now=0.0)

    outcomes = assembler.sweep_timeouts(now=15.0)
    assert len(outcomes) == 1
    assert outcomes[0].status is AssemblyStatus.REJECTED
    assert outcomes[0].reason == REASON_INCOMPLETE_TIMEOUT


def test_sweep_before_timeout_does_nothing() -> None:
    assembler = _assembler(timeout_seconds=10.0)
    events = events_for_sample(asset_id="a1", timestamp=_T0)
    for event in events[:-1]:
        assembler.ingest(event, now=0.0)

    assert assembler.sweep_timeouts(now=5.0) == []


def test_late_sample_is_rejected() -> None:
    assembler = _assembler()
    first_events = events_for_sample(asset_id="a1", timestamp=_T0)
    for event in first_events:
        assembler.ingest(event, now=0.0)

    late_events = events_for_sample(asset_id="a1", timestamp=_T0 - timedelta(seconds=5))
    outcomes = assembler.ingest(late_events[0], now=1.0)
    assert outcomes[0].status is AssemblyStatus.REJECTED
    assert outcomes[0].reason == REASON_LATE


def test_same_timestamp_as_last_processed_is_rejected_as_late() -> None:
    assembler = _assembler()
    events = events_for_sample(asset_id="a1", timestamp=_T0)
    for event in events:
        assembler.ingest(event, now=0.0)

    repeat_outcomes = assembler.ingest(events[0], now=1.0)
    assert repeat_outcomes[0].status is AssemblyStatus.REJECTED
    assert repeat_outcomes[0].reason == REASON_LATE


def test_independent_assets_do_not_interfere() -> None:
    assembler = _assembler()
    a1_events = events_for_sample(asset_id="a1", timestamp=_T0)
    a2_events = events_for_sample(asset_id="a2", timestamp=_T0)

    for event in a1_events[:-1]:
        assembler.ingest(event, now=0.0)
    for event in a2_events:
        outcomes = assembler.ingest(event, now=0.0)
    assert outcomes[-1].status is AssemblyStatus.COMPLETE
    assert assembler.buffered_timestamp_count("a1") == 1
    assert assembler.buffered_timestamp_count("a2") == 0


def test_no_cross_asset_mixing_in_completed_sample() -> None:
    assembler = _assembler()
    a1_events = events_for_sample(asset_id="a1", timestamp=_T0)
    a2_events = events_for_sample(asset_id="a2", timestamp=_T0)

    for event in a1_events[:-1]:
        assembler.ingest(event, now=0.0)
    for event in a2_events[:-1]:
        assembler.ingest(event, now=0.0)
    final = assembler.ingest(a1_events[-1], now=0.0)
    sample = final[-1].sample
    assert sample is not None
    assert sample.asset_id == "a1"


def test_buffered_timestamps_per_asset_are_bounded() -> None:
    assembler = _assembler(max_buffered_timestamps_per_asset=2)
    for i in range(3):
        timestamp = _T0 + timedelta(seconds=i)
        events = events_for_sample(asset_id="a1", timestamp=timestamp)
        # only partially complete each one so it stays buffered
        assembler.ingest(events[0], now=float(i))

    assert assembler.buffered_timestamp_count("a1") <= 2


def test_tracked_assets_are_bounded() -> None:
    assembler = _assembler(max_tracked_assets=2)
    for i in range(3):
        asset_id = f"asset-{i}"
        events = events_for_sample(asset_id=asset_id, timestamp=_T0)
        assembler.ingest(events[0], now=0.0)

    assert assembler.tracked_asset_count <= 2

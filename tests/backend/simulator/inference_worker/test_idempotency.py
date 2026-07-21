"""Idempotency specification (PR177 spec sections 6, 17 "Idempotency").

Delivery is at-least-once; correctness instead comes from deterministic
downstream event identity (`identity.deterministic_event_id`) plus the
assembler's own duplicate-measurement handling, both already covered
individually in `test_events.py`/`test_assembly.py`. This module proves
those two guarantees compose: replaying the *same* telemetry through the
worker never advances a session twice and never mints a second event_id
for the same logical output.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from backend.simulator.inference.session import FaultInferenceManager
from backend.simulator.inference_worker.assembly import SampleAssembler
from backend.simulator.inference_worker.config import InferenceWorkerSettings
from backend.simulator.inference_worker.identity import deterministic_event_id
from backend.simulator.inference_worker.worker import FaultInferenceStreamingWorker

from .conftest import TinyRuntimeFixture, events_for_sample

_ASSET_ID = "fuel-cell-stack-01"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class _FakeRecord:
    value: bytes


@dataclass
class _FakeProducer:
    sent: list[tuple[str, str, dict]] = field(default_factory=list)


def _monkeypatch_publish(
    monkeypatch: pytest.MonkeyPatch, producer: _FakeProducer
) -> None:
    def fake_publish_with_retry(_producer, *, topic, key, value, **_kwargs):
        producer.sent.append((topic, key, value))
        return True

    import backend.simulator.inference_worker.worker as worker_module

    monkeypatch.setattr(
        worker_module.kafka_io, "publish_with_retry", fake_publish_with_retry
    )


def test_deterministic_event_id_is_pure() -> None:
    first = deterministic_event_id("a", "b", "c")
    second = deterministic_event_id("a", "b", "c")
    third = deterministic_event_id("a", "b", "d")
    assert first == second
    assert first != third


def test_duplicate_measurement_event_does_not_advance_session_twice(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    manager = FaultInferenceManager(system=tiny_runtime_fixture.system)
    assembler = SampleAssembler(
        timeout_seconds=30.0, max_buffered_timestamps_per_asset=8, max_tracked_assets=64
    )
    settings = InferenceWorkerSettings(publish_max_retries=0)
    worker = FaultInferenceStreamingWorker(
        consumer=None, producer=producer, manager=manager, assembler=assembler,
        settings=settings,
    )
    session = manager.session_for(_ASSET_ID)

    events = events_for_sample(asset_id=_ASSET_ID, timestamp=_T0)
    for event in events[:-1]:
        record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
        worker._handle_message(record)
    assert session.samples_ingested == 0

    # Replay the first measurement event again before completing the sample.
    replay_record = _FakeRecord(value=json.dumps(events[0].to_json_dict()).encode())
    worker._handle_message(replay_record)
    assert session.samples_ingested == 0  # still not advanced

    final_record = _FakeRecord(value=json.dumps(events[-1].to_json_dict()).encode())
    worker._handle_message(final_record)
    assert session.samples_ingested == 1

    # Exactly one complete-sample outcome was published overall — the
    # replayed measurement never produced a second publish.
    assert len(producer.sent) == 1


def test_replayed_full_sample_after_completion_is_rejected_as_late(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replaying an already-processed sample's messages (e.g. after a
    consumer-group rebalance re-delivers committed-but-unacked messages)
    never re-advances the session — the assembler's `late` check catches
    it and reports a data-quality event instead."""
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    manager = FaultInferenceManager(system=tiny_runtime_fixture.system)
    assembler = SampleAssembler(
        timeout_seconds=30.0, max_buffered_timestamps_per_asset=8, max_tracked_assets=64
    )
    settings = InferenceWorkerSettings(publish_max_retries=0)
    worker = FaultInferenceStreamingWorker(
        consumer=None, producer=producer, manager=manager, assembler=assembler,
        settings=settings,
    )
    session = manager.session_for(_ASSET_ID)

    events = events_for_sample(asset_id=_ASSET_ID, timestamp=_T0)
    for event in events:
        record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
        worker._handle_message(record)
    assert session.samples_ingested == 1

    producer.sent.clear()
    for event in events:
        record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
        worker._handle_message(record)

    assert session.samples_ingested == 1  # unchanged
    reasons = {m["reason"] for _t, _k, m in producer.sent}
    assert reasons == {"late"}

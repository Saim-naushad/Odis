"""Restart behavior (PR177 spec sections 7, 17 "Restart").

`FaultInferenceManager`/`FaultInferenceSession` already have no
persistence (PR176, `docs/runtime-inference.md`'s "Restart / state
limitations"); this module proves the streaming layer built on top of
them doesn't invent any hidden persistence either — a fresh worker
process (fresh manager + fresh assembler) always starts cold, and
replaying already-seen telemetry into that fresh state is still safe
(handled as ordinary new samples, not corrupted duplicates, since there
is no prior state for them to conflict with).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from backend.simulator.inference.session import FaultInferenceManager
from backend.simulator.inference_worker.assembly import SampleAssembler
from backend.simulator.inference_worker.config import InferenceWorkerSettings
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


def _build_worker(
    fixture: TinyRuntimeFixture, producer: _FakeProducer
) -> FaultInferenceStreamingWorker:
    manager = FaultInferenceManager(system=fixture.system)
    assembler = SampleAssembler(
        timeout_seconds=30.0, max_buffered_timestamps_per_asset=8, max_tracked_assets=64
    )
    return FaultInferenceStreamingWorker(
        consumer=None,
        producer=producer,
        manager=manager,
        assembler=assembler,
        settings=InferenceWorkerSettings(publish_max_retries=0),
    )


def test_new_worker_process_begins_warming_up_again(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)

    first_worker = _build_worker(tiny_runtime_fixture, producer)
    events = events_for_sample(asset_id=_ASSET_ID, timestamp=_T0)
    for event in events:
        record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
        first_worker._handle_message(record)
    assert first_worker._manager.session_for(_ASSET_ID).samples_ingested == 1

    # Simulate a restart: a brand-new worker process constructs a brand-new
    # manager/assembler — no state is carried across processes by design.
    producer.sent.clear()
    second_worker = _build_worker(tiny_runtime_fixture, producer)
    assert second_worker._manager.session_for(_ASSET_ID).samples_ingested == 0

    later_timestamp = _T0.replace(second=1)
    for event in events_for_sample(asset_id=_ASSET_ID, timestamp=later_timestamp):
        record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
        second_worker._handle_message(record)
    assert second_worker._manager.session_for(_ASSET_ID).samples_ingested == 1
    results = [m for topic, _k, m in producer.sent if m.get("status") == "warming_up"]
    assert len(results) == 1


def test_replaying_pre_restart_telemetry_into_a_fresh_worker_is_safe(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fresh worker (post-restart) has no record of what the previous
    process already processed, so offset replay from before the restart
    is handled as ordinary — safe — re-ingestion, not corruption. This is
    the documented limitation: no cross-process dedup exists for input
    telemetry, only for the worker's own *output* event identity."""
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)

    worker = _build_worker(tiny_runtime_fixture, producer)
    events = events_for_sample(asset_id=_ASSET_ID, timestamp=_T0)
    for event in events:
        record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
        worker._handle_message(record)  # does not raise
    assert worker._manager.session_for(_ASSET_ID).samples_ingested == 1

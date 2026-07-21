"""`FaultInferenceStreamingWorker` behavior (PR177 spec sections 5, 6, 17
"Worker behavior" / "Idempotency")."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from backend.simulator.dataset.features.config import LONGEST_WINDOW_SAMPLES
from backend.simulator.dataset.features.safety import MIN_ABS_FUEL_FLOW_SLPM
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
    fail_topics: set[str] = field(default_factory=set)
    sent: list[tuple[str, str, dict]] = field(default_factory=list)

    def send_json(self, topic: str, *, key: str, value: dict) -> None:
        if topic in self.fail_topics:
            raise RuntimeError("publish failed")
        self.sent.append((topic, key, value))


def _settings(**overrides: object) -> InferenceWorkerSettings:
    defaults: dict[str, object] = {
        "publish_max_retries": 0,
        "publish_retry_backoff_seconds": 0.001,
        "results_topic": "results",
        "alert_transitions_topic": "transitions",
        "data_quality_topic": "data-quality",
    }
    defaults.update(overrides)
    return InferenceWorkerSettings(**defaults)  # type: ignore[arg-type]


def _worker(
    fixture: TinyRuntimeFixture,
    *,
    producer: _FakeProducer,
    settings: InferenceWorkerSettings | None = None,
) -> FaultInferenceStreamingWorker:
    manager = FaultInferenceManager(system=fixture.system)
    assembler = SampleAssembler(
        timeout_seconds=30.0,
        max_buffered_timestamps_per_asset=8,
        max_tracked_assets=64,
    )
    return FaultInferenceStreamingWorker(
        consumer=None,
        producer=producer,
        manager=manager,
        assembler=assembler,
        settings=settings or _settings(),
    )


def _monkeypatch_publish(
    monkeypatch: pytest.MonkeyPatch, producer: _FakeProducer
) -> None:
    def fake_publish_with_retry(_producer, *, topic, key, value, **_kwargs):
        producer.send_json(topic, key=key, value=value)
        return True

    def fake_publish_with_failure(_producer, *, topic, key, value, **_kwargs):
        if topic in producer.fail_topics:
            return False
        producer.send_json(topic, key=key, value=value)
        return True

    import backend.simulator.inference_worker.worker as worker_module

    monkeypatch.setattr(
        worker_module.kafka_io, "publish_with_retry", fake_publish_with_failure
    )


def test_complete_sample_produces_exactly_one_result_event(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(tiny_runtime_fixture, producer=producer)

    for event in events_for_sample(asset_id=_ASSET_ID, timestamp=_T0):
        record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
        ok = worker._handle_message(record)
        assert ok is True

    results = [m for topic, _k, m in producer.sent if topic == "results"]
    assert len(results) == 1
    assert results[0]["status"] == "warming_up"


def test_malformed_event_routes_to_data_quality_and_does_not_crash(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(tiny_runtime_fixture, producer=producer)

    record = _FakeRecord(value=b"not json at all")
    ok = worker._handle_message(record)

    assert ok is True
    dq_messages = [m for topic, _k, m in producer.sent if topic == "data-quality"]
    assert len(dq_messages) == 1
    assert dq_messages[0]["reason"] == "malformed"


def test_publish_failure_returns_false_and_does_not_advance_offset(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer(fail_topics={"results"})
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(tiny_runtime_fixture, producer=producer)

    ok = True
    for i in range(LONGEST_WINDOW_SAMPLES):
        timestamp = _T0 + timedelta(seconds=i)
        for event in events_for_sample(asset_id=_ASSET_ID, timestamp=timestamp):
            record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
            ok = worker._handle_message(record)
        if not ok:
            break

    assert ok is False
    assert all(topic != "results" for topic, _k, _v in producer.sent)


def test_warming_up_result_is_emitted(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(tiny_runtime_fixture, producer=producer)

    for event in events_for_sample(asset_id=_ASSET_ID, timestamp=_T0):
        record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
        worker._handle_message(record)

    results = [m for topic, _k, m in producer.sent if topic == "results"]
    assert results[0]["status"] == "warming_up"


def test_insufficient_data_result_is_emitted(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(tiny_runtime_fixture, producer=producer)

    for i in range(LONGEST_WINDOW_SAMPLES):
        timestamp = _T0 + timedelta(seconds=i)
        values = None
        if i == LONGEST_WINDOW_SAMPLES - 1:
            values = {"fuel_flow": MIN_ABS_FUEL_FLOW_SLPM / 2}
        for event in events_for_sample(
            asset_id=_ASSET_ID, timestamp=timestamp, values=values
        ):
            record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
            worker._handle_message(record)

    results = [m for topic, _k, m in producer.sent if topic == "results"]
    assert results[-1]["status"] == "insufficient_data"


def test_alert_transition_emitted_only_on_transition(
    tiny_runtime_fixture: TinyRuntimeFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)

    system = tiny_runtime_fixture.system
    entry_persistence = system.alert_policy_config.entry_persistence
    n_predictions = entry_persistence + 3

    class _FakeSequencePipeline:
        def __init__(self, proba):
            self._proba = proba
            self._calls = 0

        def predict_proba(self, x):
            row = self._proba[min(self._calls, len(self._proba) - 1)]
            self._calls += 1
            return np.array([row])

    def _row(**by_class):
        remainder_classes = [c for c in system.class_order if c not in by_class]
        assigned = sum(by_class.values())
        remainder = (
            (1.0 - assigned) / len(remainder_classes) if remainder_classes else 0.0
        )
        return np.array(
            [by_class.get(c, remainder) for c in system.class_order], dtype=float
        )

    fault_row = _row(cooling_degradation=0.99)
    scripted_system = replace(
        system, pipeline=_FakeSequencePipeline([fault_row] * n_predictions)
    )
    manager = FaultInferenceManager(system=scripted_system)
    assembler = SampleAssembler(
        timeout_seconds=30.0, max_buffered_timestamps_per_asset=8, max_tracked_assets=64
    )
    worker = FaultInferenceStreamingWorker(
        consumer=None,
        producer=producer,
        manager=manager,
        assembler=assembler,
        settings=_settings(),
    )

    total = LONGEST_WINDOW_SAMPLES - 1 + n_predictions
    for i in range(total):
        timestamp = _T0 + timedelta(seconds=i)
        for event in events_for_sample(asset_id=_ASSET_ID, timestamp=timestamp):
            record = _FakeRecord(value=json.dumps(event.to_json_dict()).encode())
            worker._handle_message(record)

    transitions = [m for topic, _k, m in producer.sent if topic == "transitions"]
    assert len(transitions) == 1
    assert transitions[0]["transition_type"] == "confirmed"

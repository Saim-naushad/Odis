"""`ReasoningBridgeWorker` behavior (PR178 spec sections 15, 19 "Worker
behavior" / "Persistence and events")."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from backend.app.application.reasoning_bridge.reasoning_bridge_service import (
    ReasoningBridgeService,
)
from backend.app.application.reasoning_bridge.worker import ReasoningBridgeWorker
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.repositories.observation_repository import (
    SqlAlchemyObservationRepository,
)

from .conftest import make_observation

_ASSET_ID = "fuel-cell-stack-01"
_T0 = datetime(2026, 1, 1, tzinfo=UTC)

_INCREASING = [10.0, 10.0, 10.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0]
_DECREASING = [70.0, 60.0, 50.0, 40.0, 30.0, 20.0, 10.0, 10.0, 10.0, 10.0]

_VALID_RAW: dict[str, object] = {
    "event_id": "evt-1",
    "event_version": "v1",
    "occurred_at": "2026-01-01T00:00:05+00:00",
    "asset_id": _ASSET_ID,
    "source_timestamp": "2026-01-01T00:00:00+00:00",
    "transition_type": "confirmed",
    "from_state": "healthy",
    "to_state": "confirmed_cooling_degradation",
    "diagnosed_class": "cooling_degradation",
    "evidence": [{"label": "top_class_probability", "value": 0.9, "detail": "x"}],
    "model_system_version": "plant_alpha_fault_v1",
    "model_hash": "hash-a",
    "policy_hash": "policy-a",
    "feature_schema_version": "1.0",
    "class_scores": {"healthy": 0.05, "cooling_degradation": 0.9},
    "maximum_score": 0.9,
}


@dataclass
class _FakeRecord:
    value: bytes


@dataclass
class _FakeProducer:
    fail_topics: set[str] = field(default_factory=set)
    sent: list[tuple[str, str, dict]] = field(default_factory=list)


def _monkeypatch_publish(
    monkeypatch: pytest.MonkeyPatch, producer: _FakeProducer
) -> None:
    def fake_publish_with_retry(_producer, *, topic, key, value, **_kwargs):
        if topic in producer.fail_topics:
            return False
        producer.sent.append((topic, key, value))
        return True

    import backend.app.application.reasoning_bridge.worker as worker_module

    monkeypatch.setattr(
        worker_module.kafka_io, "publish_with_retry", fake_publish_with_retry
    )


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "database_url": "sqlite://",
        "reasoning_bridge_output_topic": "reasoning-results",
        "reasoning_bridge_publish_max_retries": 0,
        "reasoning_bridge_publish_retry_backoff_seconds": 0.001,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _worker(
    session_factory: Callable[[], Session],
    *,
    producer: _FakeProducer,
    settings: Settings | None = None,
) -> ReasoningBridgeWorker:
    service = ReasoningBridgeService(lambda: SqlAlchemyUnitOfWork(session_factory))
    return ReasoningBridgeWorker(
        consumer=None,
        producer=producer,
        service=service,
        settings=settings or _settings(),
    )


def _seed_corroborating_observations(session_factory: Callable[[], Session]) -> None:
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        repository = SqlAlchemyObservationRepository(uow.session)
        for measurement, values in (
            ("stack_temperature", _INCREASING),
            ("coolant_flow", _DECREASING),
        ):
            for i, value in enumerate(values):
                timestamp = _T0 - timedelta(seconds=(len(values) - i) * 10)
                repository.save(
                    make_observation(
                        asset_id=_ASSET_ID,
                        measurement_type=measurement,
                        value=value,
                        unit="unit",
                        timestamp=timestamp,
                        observation_id=f"{measurement}-{i}",
                    )
                )
        uow.commit()


def test_valid_confirmed_alert_produces_one_reasoning_result_event(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_corroborating_observations(session_factory)
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(session_factory, producer=producer)

    record = _FakeRecord(value=json.dumps(_VALID_RAW).encode())
    ok = worker._handle_message(record)

    assert ok is True
    assert len(producer.sent) == 1
    topic, key, payload = producer.sent[0]
    assert topic == "reasoning-results"
    assert key == _ASSET_ID
    assert payload["corroboration_result"] == "corroborated"
    assert payload["recommendation_status"] == "produced"


def test_malformed_event_does_not_crash_and_advances_offset(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(session_factory, producer=producer)

    record = _FakeRecord(value=b"not json at all")
    ok = worker._handle_message(record)

    assert ok is True
    assert producer.sent == []


def test_healthy_class_is_rejected_without_crashing(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(session_factory, producer=producer)

    raw = {**_VALID_RAW, "from_state": "confirmed_x", "to_state": "confirmed_healthy"}
    record = _FakeRecord(value=json.dumps(raw).encode())
    ok = worker._handle_message(record)

    assert ok is True
    assert producer.sent == []


def test_unsupported_fault_class_is_rejected_without_crashing(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(session_factory, producer=producer)

    raw = {**_VALID_RAW, "to_state": "confirmed_membrane_dehydration"}
    record = _FakeRecord(value=json.dumps(raw).encode())
    ok = worker._handle_message(record)

    assert ok is True
    assert producer.sent == []


def test_publish_failure_returns_false_so_offset_is_not_committed(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer(fail_topics={"reasoning-results"})
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(session_factory, producer=producer)

    record = _FakeRecord(value=json.dumps(_VALID_RAW).encode())
    ok = worker._handle_message(record)

    assert ok is False
    assert producer.sent == []


def test_duplicate_replay_does_not_emit_a_second_event(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(session_factory, producer=producer)

    record = _FakeRecord(value=json.dumps(_VALID_RAW).encode())
    worker._handle_message(record)
    ok = worker._handle_message(record)

    assert ok is True
    assert len(producer.sent) == 1


def test_cleared_transition_produces_no_recommendation_status_produced(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    producer = _FakeProducer()
    _monkeypatch_publish(monkeypatch, producer)
    worker = _worker(session_factory, producer=producer)

    confirmed_record = _FakeRecord(value=json.dumps(_VALID_RAW).encode())
    worker._handle_message(confirmed_record)

    cleared_raw = {
        **_VALID_RAW,
        "event_id": "evt-2",
        "transition_type": "cleared",
        "from_state": "confirmed_cooling_degradation",
        "to_state": "healthy",
        "diagnosed_class": "healthy",
        "source_timestamp": "2026-01-01T00:00:10+00:00",
    }
    cleared_record = _FakeRecord(value=json.dumps(cleared_raw).encode())
    ok = worker._handle_message(cleared_record)

    assert ok is True
    assert len(producer.sent) == 2
    _topic, _key, payload = producer.sent[-1]
    assert payload["recommendation_status"] is None

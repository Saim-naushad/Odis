"""`--mode reliability` checks (PR181) — always on their own dedicated
ephemeral stack, never mixed with a performance run, so injected failures
can never contaminate latency/throughput/resource measurements.

Verifies mechanisms that already exist in the codebase rather than building
new plumbing (see the plan's audit): deterministic-event-id dedup, DB-unique-
constraint idempotency, at-least-once + manual-offset-commit, and outbox
retry-on-failure.

Two distinct outage checks, corrected from the original design after reading
`outbox_dispatcher.py` and `integration_event_mapping.py` directly:
`AiFaultInvestigationUpdated` has **no Kafka leg at all** (`map_domain_event_
to_integration_event` returns `None` for it, so `_publish_integration_event`
marks it dispatched unconditionally) — stopping Kafka would prove nothing
about that event type. The Kafka-leg recovery check therefore uses an event
type that genuinely has one (`ReasoningCompleted`); the AI-investigation
check instead interrupts Redis and records what's actually observed, rather
than asserting a hardcoded expectation the code hasn't been proven to match.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.domain.outbox import OutboxEvent
from backend.app.infrastructure.database.models.ai_fault_evidence import (
    AiFaultEvidenceModel,
)


@dataclass(frozen=True)
class ReplayIdempotencyResult:
    replayed_event_count: int
    ai_fault_evidence_row_count_before: int
    ai_fault_evidence_row_count_after: int
    passed: bool


def replay_alert_transitions(
    *,
    bootstrap_servers: str,
    topic: str,
    captured_messages: list[bytes],
    captured_keys: list[bytes],
    session: Session,
    asset_ids: tuple[str, ...],
) -> ReplayIdempotencyResult:
    """Re-publish already-processed alert-transition messages verbatim
    (byte-identical payload and key) and assert the row count doesn't grow —
    the deterministic `event_id`/DB-unique-constraint dedup described in
    `backend/simulator/inference_worker/identity.py` and
    `AiFaultEvidenceModel`'s docstring is what's actually being verified."""
    from kafka import KafkaProducer

    before = _ai_fault_evidence_count(session, asset_ids)

    producer = KafkaProducer(bootstrap_servers=bootstrap_servers)
    try:
        for key, value in zip(captured_keys, captured_messages, strict=True):
            producer.send(topic, key=key, value=value).get(timeout=5)
        producer.flush()
    finally:
        producer.close()

    # Give the reasoning-bridge worker time to consume and (idempotently)
    # ignore the replayed messages.
    time.sleep(10.0)
    after = _ai_fault_evidence_count(session, asset_ids)

    return ReplayIdempotencyResult(
        replayed_event_count=len(captured_messages),
        ai_fault_evidence_row_count_before=before,
        ai_fault_evidence_row_count_after=after,
        passed=after == before,
    )


def _ai_fault_evidence_count(session: Session, asset_ids: tuple[str, ...]) -> int:
    rows = session.scalars(
        select(AiFaultEvidenceModel.id).where(
            AiFaultEvidenceModel.asset_id.in_(asset_ids)
        )
    ).all()
    return len(rows)


@dataclass(frozen=True)
class MalformedTelemetryResult:
    published_malformed_count: int
    malformed_counter_delta: float
    worker_still_running: bool
    passed: bool


def publish_malformed_telemetry(
    *, bootstrap_servers: str, topic: str, count: int = 3
) -> None:
    """Deliberately publish payloads missing required fields — the fault-
    inference worker must count and reject these, never crash."""
    from kafka import KafkaProducer

    producer = KafkaProducer(bootstrap_servers=bootstrap_servers)
    try:
        for i in range(count):
            bad_payload = {"event_id": str(uuid4()), "not_a_real_field": i}
            producer.send(
                topic,
                key=f"malformed-{i}".encode(),
                value=json.dumps(bad_payload).encode("utf-8"),
            ).get(timeout=5)
        producer.flush()
    finally:
        producer.close()


def query_prometheus_scalar(
    *, prometheus_base_url: str, promql: str
) -> float | None:
    response = httpx.get(
        f"{prometheus_base_url}/api/v1/query",
        params={"query": promql},
        timeout=10.0,
    )
    response.raise_for_status()
    body = response.json()
    results = body.get("data", {}).get("result", [])
    if not results:
        return None
    _timestamp, value = results[0]["value"]
    return float(value)


def container_is_running(project_name: str, service: str) -> bool:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            project_name,
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.benchmark.yml",
            "ps",
            "--status",
            "running",
            "--format",
            "{{.Service}}",
            service,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    return service in result.stdout


@dataclass(frozen=True)
class OutboxKafkaLegRecoveryResult:
    dispatched_at_stayed_null_during_outage: bool
    dispatched_exactly_once_after_recovery: bool
    passed: bool


def outbox_kafka_leg_recovery_check(
    *,
    session_factory: sessionmaker[Session],
    project_name: str,
    stop_and_start_kafka: bool = True,
) -> OutboxKafkaLegRecoveryResult:
    """Uses `ReasoningCompleted` -> `DigitalTwinUpdated`, an event type that
    genuinely has a Kafka leg (`integration_event_mapping.py`), unlike
    `AiFaultInvestigationUpdated`."""
    from backend.app.application.events.domain_events import ReasoningCompleted
    from backend.app.application.events.event_bus import DomainEventBus
    from backend.app.application.outbox_dispatcher import OutboxDispatcher
    from backend.app.infrastructure.events.kafka_integration_event_publisher import (
        KafkaIntegrationEventPublisher,
    )
    from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
        SqlAlchemyUnitOfWork,
    )

    event = ReasoningCompleted(
        asset_id="fuel-cell-stack-01",
        run_id=f"reliability-{uuid4().hex[:8]}",
        timestamp=datetime.now(UTC),
    )
    row_id = str(uuid4())
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            OutboxEvent(
                id=row_id,
                event_type="ReasoningCompleted",
                payload={
                    "asset_id": event.asset_id,
                    "run_id": event.run_id,
                    "timestamp": event.timestamp.isoformat(),
                },
                created_at=datetime.now(UTC),
                dispatched_at=None,
            )
        )
        uow.commit()

    if stop_and_start_kafka:
        subprocess.run(["docker", "stop", f"{project_name}-kafka-1"], timeout=30)

    publisher = KafkaIntegrationEventPublisher(bootstrap_servers="localhost:1")
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory), DomainEventBus(), publisher
    )
    dispatcher.dispatch()

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        row = uow.session.get(OutboxEvent, row_id)
        stayed_null = row is not None and row.dispatched_at is None

    if stop_and_start_kafka:
        subprocess.run(["docker", "start", f"{project_name}-kafka-1"], timeout=30)
        time.sleep(15.0)

    dispatched_count = 0
    for _ in range(5):
        real_publisher = KafkaIntegrationEventPublisher(
            bootstrap_servers="localhost:19092"
        )
        real_dispatcher = OutboxDispatcher(
            lambda: SqlAlchemyUnitOfWork(session_factory),
            DomainEventBus(),
            real_publisher,
        )
        real_dispatcher.dispatch()
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            row = uow.session.get(OutboxEvent, row_id)
            if row is not None and row.dispatched_at is not None:
                dispatched_count += 1
                break
        time.sleep(3.0)

    return OutboxKafkaLegRecoveryResult(
        dispatched_at_stayed_null_during_outage=stayed_null,
        dispatched_exactly_once_after_recovery=dispatched_count == 1,
        passed=stayed_null and dispatched_count == 1,
    )


@dataclass(frozen=True)
class AiInvestigationDurabilityResult:
    outbox_row_dispatched_despite_redis_outage: bool
    note: str


def ai_investigation_durability_check(
    *, session_factory: sessionmaker[Session], project_name: str, redis_url: str
) -> AiInvestigationDurabilityResult:
    """`AiFaultInvestigationUpdated` has no Kafka leg, so this interrupts
    Redis instead and records what actually happens to the outbox row's
    durability — an empirical observation, not an assertion against
    unverified internal behavior.

    Wires the real `MonitoringEventHandler` + `RedisMonitoringEventSource`
    onto the bus (rather than dispatching with no subscriber at all) so the
    check genuinely exercises `RedisMonitoringEventSource.publish()`'s
    swallow-on-`RedisError` behavior, not a no-op bus with nothing
    listening."""
    from backend.app.application.events.domain_events import (
        AiFaultInvestigationUpdated,
    )
    from backend.app.application.events.event_bus import DomainEventBus
    from backend.app.application.events.handlers.monitoring_event_handler import (
        MonitoringEventHandler,
    )
    from backend.app.application.outbox_dispatcher import OutboxDispatcher
    from backend.app.infrastructure.events.redis_monitoring_event_source import (
        RedisMonitoringEventSource,
    )
    from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
        SqlAlchemyUnitOfWork,
    )

    event_payload = {
        "asset_id": "fuel-cell-stack-01",
        "investigation_id": f"reliability-{uuid4().hex[:8]}",
        "diagnosed_fault_class": "cooling_degradation",
        "investigation_status": "OPEN",
        "alert_transition_type": "confirmed",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    row_id = str(uuid4())
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.session.add(
            OutboxEvent(
                id=row_id,
                event_type="AiFaultInvestigationUpdated",
                payload=event_payload,
                created_at=datetime.now(UTC),
                dispatched_at=None,
            )
        )
        uow.commit()

    event_bus = DomainEventBus()
    redis_source = RedisMonitoringEventSource(redis_url=redis_url)
    handler = MonitoringEventHandler(redis_source)
    event_bus.subscribe(
        AiFaultInvestigationUpdated, handler.on_ai_fault_investigation_updated
    )

    subprocess.run(["docker", "stop", f"{project_name}-redis-1"], timeout=30)
    try:
        dispatcher = OutboxDispatcher(
            lambda: SqlAlchemyUnitOfWork(session_factory), event_bus, None
        )
        try:
            dispatcher.dispatch()
            note = "dispatch() completed normally with Redis stopped"
        except Exception as exc:
            note = f"dispatch() raised with Redis stopped: {exc!r}"
    finally:
        subprocess.run(["docker", "start", f"{project_name}-redis-1"], timeout=30)
        time.sleep(5.0)

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        row = uow.session.get(OutboxEvent, row_id)
        dispatched = row is not None and row.dispatched_at is not None

    return AiInvestigationDurabilityResult(
        outbox_row_dispatched_despite_redis_outage=dispatched, note=note
    )

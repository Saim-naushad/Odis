"""After-the-fact/pull measurements taken during or after a run (PR181):
Postgres reconciliation queries, Kafka consumer-lag, and continuous `docker
stats` resource sampling.

Distinct from `observers.py`'s live, concurrent, push-based channels — these
are point-in-time (or periodic) queries against durable/external state.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.domain.outbox import OutboxEvent
from backend.app.infrastructure.database.models.ai_fault_evidence import (
    AiFaultEvidenceModel,
)
from backend.app.infrastructure.database.models.observation import ObservationModel
from backend.app.infrastructure.database.models.timeline_event import (
    TimelineEventModel,
)

# Compose defaults (docker-compose.yml) — the benchmark stack never
# overrides these, so the real pipeline workers always use them.
FAULT_INFERENCE_CONSUMER_GROUP = "odis-fault-inference-worker"
REASONING_BRIDGE_CONSUMER_GROUP = "odis-reasoning-bridge"


@dataclass(frozen=True)
class AiFaultEvidenceRow:
    source_event_id: str
    asset_id: str
    observed_at: datetime
    recorded_at: datetime
    investigation_id: str
    investigation_status: str
    has_recommendation: bool


def query_ai_fault_evidence(
    session: Session, asset_ids: tuple[str, ...]
) -> list[AiFaultEvidenceRow]:
    rows = session.scalars(
        select(AiFaultEvidenceModel).where(
            AiFaultEvidenceModel.asset_id.in_(asset_ids)
        )
    ).all()
    return [
        AiFaultEvidenceRow(
            source_event_id=row.source_event_id,
            asset_id=row.asset_id,
            observed_at=row.observed_at,
            recorded_at=row.recorded_at,
            investigation_id=row.investigation_id,
            investigation_status=row.investigation_status,
            has_recommendation=row.recommendation is not None,
        )
        for row in rows
    ]


@dataclass(frozen=True)
class ReconciliationCounts:
    observation_rows: int
    timeline_event_rows: int
    ai_fault_evidence_rows: int
    outbox_pending_rows: int
    distinct_investigation_ids: int


def reconcile_counts(
    session: Session, asset_ids: tuple[str, ...]
) -> ReconciliationCounts:
    observation_rows = session.scalar(
        select(func.count())
        .select_from(ObservationModel)
        .where(ObservationModel.asset_id.in_(asset_ids))
    ) or 0
    timeline_event_rows = session.scalar(
        select(func.count())
        .select_from(TimelineEventModel)
        .where(TimelineEventModel.asset_id.in_(asset_ids))
    ) or 0
    ai_fault_evidence_rows = session.scalar(
        select(func.count())
        .select_from(AiFaultEvidenceModel)
        .where(AiFaultEvidenceModel.asset_id.in_(asset_ids))
    ) or 0
    outbox_pending_rows = session.scalar(
        select(func.count())
        .select_from(OutboxEvent)
        .where(OutboxEvent.dispatched_at.is_(None))
    ) or 0
    distinct_investigation_ids = session.scalar(
        select(func.count(func.distinct(AiFaultEvidenceModel.investigation_id))).where(
            AiFaultEvidenceModel.asset_id.in_(asset_ids)
        )
    ) or 0
    return ReconciliationCounts(
        observation_rows=observation_rows,
        timeline_event_rows=timeline_event_rows,
        ai_fault_evidence_rows=ai_fault_evidence_rows,
        outbox_pending_rows=outbox_pending_rows,
        distinct_investigation_ids=distinct_investigation_ids,
    )


def consumer_lag(
    *, bootstrap_servers: str, group_id: str, topics: tuple[str, ...]
) -> dict[str, int]:
    """Sum of (end_offset - committed_offset) per topic for `group_id`.

    No lag exporter exists in this stack (no cAdvisor/Burrow/etc) — this
    uses `kafka-python` (already a dependency) directly, the same client
    every other Kafka user in this codebase relies on.
    """
    from kafka import KafkaConsumer, TopicPartition

    consumer = KafkaConsumer(
        bootstrap_servers=bootstrap_servers,
        group_id=group_id,
        enable_auto_commit=False,
    )
    try:
        lag_by_topic: dict[str, int] = {}
        for topic in topics:
            partitions = consumer.partitions_for_topic(topic) or set()
            topic_partitions = [TopicPartition(topic, p) for p in partitions]
            if not topic_partitions:
                lag_by_topic[topic] = 0
                continue
            end_offsets = consumer.end_offsets(topic_partitions)
            committed = {
                tp: (consumer.committed(tp) or 0) for tp in topic_partitions
            }
            lag_by_topic[topic] = sum(
                max(0, end_offsets[tp] - committed[tp]) for tp in topic_partitions
            )
        return lag_by_topic
    finally:
        consumer.close()


@dataclass(frozen=True)
class ResourceSample:
    taken_at: float  # time.monotonic() - relative, for interval math only
    container: str
    cpu_percent: float
    memory_bytes: float


class DockerStatsSampler:
    """Continuously samples `docker stats` for the given containers at a
    fixed interval (default 1 Hz) for the run's full duration — never a
    handful of checkpoints, per the resource-sampling correction.

    Docker's CPU% is relative to a single core (100% == one full core
    saturated; can exceed 100% for a multi-threaded container on a
    multi-core host) — callers/report.py must state this explicitly.
    """

    def __init__(
        self, *, containers: tuple[str, ...], interval_seconds: float = 1.0
    ) -> None:
        self._containers = containers
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.samples: list[ResourceSample] = []

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            taken_at = time.monotonic()
            for container in self._containers:
                sample = _docker_stats_once(container, taken_at=taken_at)
                if sample is not None:
                    with self._lock:
                        self.samples.append(sample)
            self._stop.wait(self._interval_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval_seconds + 5.0)

    def samples_for(self, container: str) -> list[ResourceSample]:
        with self._lock:
            return [s for s in self.samples if s.container == container]

    def __enter__(self) -> DockerStatsSampler:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


def _docker_stats_once(container: str, *, taken_at: float) -> ResourceSample | None:
    try:
        result = subprocess.run(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{json .}}",
                container,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        raw = json.loads(result.stdout.strip().splitlines()[0])
        cpu_percent = float(raw["CPUPerc"].rstrip("%"))
        memory_bytes = _parse_docker_memory(raw["MemUsage"].split("/")[0].strip())
    except (json.JSONDecodeError, KeyError, ValueError, IndexError):
        return None
    return ResourceSample(
        taken_at=taken_at,
        container=container,
        cpu_percent=cpu_percent,
        memory_bytes=memory_bytes,
    )


# Longest/most specific suffix first — "B" alone must be checked last, since
# "MiB"/"GiB"/"KiB" all also end with "B".
_MEMORY_UNITS = (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024), ("B", 1))


def _parse_docker_memory(raw: str) -> float:
    for unit, multiplier in _MEMORY_UNITS:
        if raw.endswith(unit):
            return float(raw[: -len(unit)]) * multiplier
    return float(raw)

#!/usr/bin/env python3
"""Benchmark reasoning worker throughput at varying observation history sizes.

Run against a live Postgres stack (Compose recommended):

    docker compose up -d postgres api worker
    python scripts/benchmark_reasoning_worker.py

Reports average/p95 job duration, throughput, and queue simulation at
presentation and realistic ingest rates.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.observation_service_factory import (
    create_observation_service,
)
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.reasoning_job_queue import DatabaseReasoningJobQueue
from backend.app.application.reasoning_worker import ReasoningWorker
from backend.app.domain.outbox import OutboxEvent
from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database.models.observation import ObservationModel
from backend.app.infrastructure.database.models.reasoning_job import ReasoningJobModel
from backend.app.infrastructure.database.models.timeline_event import (
    TimelineEventModel,
)
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.repositories.reasoning_job_repository import (
    SqlAlchemyReasoningJobRepository,
)
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

_CORE_MEASUREMENTS: tuple[tuple[str, str], ...] = (
    ("stack_temperature", "celsius"),
    ("stack_pressure", "kPa"),
    ("current", "A"),
    ("voltage", "V"),
    ("fuel_flow", "SLPM"),
)

PRESENTATION_INGEST_JOBS_PER_SEC = 20 / 15 + 12 / 60  # ~1.53
REALISTIC_INGEST_JOBS_PER_SEC = 20 / 30 + 12 / 120  # ~0.77


@dataclass(frozen=True)
class HistoryBenchmarkResult:
    history_observations: int
    benchmark_jobs: int
    avg_job_seconds: float
    p95_job_seconds: float
    throughput_jobs_per_second: float
    avg_list_by_asset_seconds: float
    presentation_queue_growth_per_min: float
    realistic_queue_growth_per_min: float
    presentation_bounded: bool
    realistic_bounded: bool


def _fuel_cell_observation(
    index: int,
    *,
    asset_id: str,
    run_id: str,
) -> Observation:
    measurement_name, unit = _CORE_MEASUREMENTS[index % len(_CORE_MEASUREMENTS)]
    cycle = index // len(_CORE_MEASUREMENTS)
    timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC) + timedelta(
        seconds=15 * cycle + (index % len(_CORE_MEASUREMENTS))
    )
    return Observation(
        id=f"bench-{run_id}-{asset_id}-i{index}-{measurement_name}",
        asset_id=asset_id,
        timestamp=timestamp,
        measurement_type=MeasurementType(name=measurement_name),
        value=60.0 + cycle * 0.05 + (index % 5) * 0.01,
        unit=unit,
    )


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return ordered[rank]


def _queue_growth_per_minute(
    *,
    ingest_jobs_per_second: float,
    drain_jobs_per_second: float,
) -> float:
    net = ingest_jobs_per_second - drain_jobs_per_second
    return net * 60.0


def _reset_asset_data(session: Session, asset_id: str) -> None:
    session.execute(
        delete(ReasoningJobModel).where(ReasoningJobModel.asset_id == asset_id),
    )
    session.execute(
        delete(ObservationModel).where(ObservationModel.asset_id == asset_id),
    )
    session.execute(
        delete(TimelineEventModel).where(TimelineEventModel.asset_id == asset_id),
    )
    session.commit()


def benchmark_history_size(
    *,
    session_factory,
    history_size: int,
    benchmark_jobs: int,
    asset_id: str,
    run_id: str,
) -> HistoryBenchmarkResult:
    event_bus = DomainEventBus()
    dispatcher = OutboxDispatcher(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        event_bus,
    )
    service = create_observation_service(
        SqlAlchemyUnitOfWork(session_factory),
        event_bus,
        dispatcher,
    )
    worker = ReasoningWorker(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        lambda uow: DatabaseReasoningJobQueue(
            SqlAlchemyReasoningJobRepository(uow.session),
        ),
        event_bus,
        dispatcher,
    )

    from backend.app.infrastructure.repositories.observation_repository import (
        SqlAlchemyObservationRepository,
    )

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        _reset_asset_data(uow.session, asset_id)
        repo = SqlAlchemyObservationRepository(uow.session)
        for index in range(history_size):
            repo.save(
                _fuel_cell_observation(
                    index,
                    asset_id=asset_id,
                    run_id=f"{run_id}-{history_size}",
                ),
            )
        uow.commit()

    while worker.process_next():
        pass

    list_durations: list[float] = []
    job_durations: list[float] = []

    for offset in range(benchmark_jobs):
        observation = _fuel_cell_observation(
            history_size + offset,
            asset_id=asset_id,
            run_id=f"{run_id}-{history_size}",
        )
        service.create(observation)

        with SqlAlchemyUnitOfWork(session_factory) as uow:
            repo = SqlAlchemyObservationRepository(uow.session)
            list_start = time.perf_counter()
            repo.list_by_asset(asset_id)
            list_durations.append(time.perf_counter() - list_start)

        start = time.perf_counter()
        processed = worker.process_next()
        if not processed:
            msg = (
                f"expected reasoning job for observation index "
                f"{history_size + offset} at history={history_size}"
            )
            raise RuntimeError(msg)
        job_durations.append(time.perf_counter() - start)

    avg_job = statistics.mean(job_durations)
    p95_job = _percentile(job_durations, 95)
    throughput = len(job_durations) / sum(job_durations)
    avg_list = statistics.mean(list_durations)

    presentation_growth = _queue_growth_per_minute(
        ingest_jobs_per_second=PRESENTATION_INGEST_JOBS_PER_SEC,
        drain_jobs_per_second=throughput,
    )
    realistic_growth = _queue_growth_per_minute(
        ingest_jobs_per_second=REALISTIC_INGEST_JOBS_PER_SEC,
        drain_jobs_per_second=throughput,
    )

    return HistoryBenchmarkResult(
        history_observations=history_size,
        benchmark_jobs=benchmark_jobs,
        avg_job_seconds=avg_job,
        p95_job_seconds=p95_job,
        throughput_jobs_per_second=throughput,
        avg_list_by_asset_seconds=avg_list,
        presentation_queue_growth_per_min=presentation_growth,
        realistic_queue_growth_per_min=realistic_growth,
        presentation_bounded=presentation_growth <= 0.0,
        realistic_bounded=realistic_growth <= 0.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://odis:odis@localhost:5432/odis",
        ),
    )
    parser.add_argument(
        "--history-sizes",
        default="100,500,1500,3000",
        help="Comma-separated observation counts per asset to benchmark",
    )
    parser.add_argument(
        "--benchmark-jobs",
        type=int,
        default=25,
        help="Fresh jobs to time after seeding each history size",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional JSON output path",
    )
    args = parser.parse_args()

    history_sizes = [int(value.strip()) for value in args.history_sizes.split(",")]
    settings = Settings(database_url=args.database_url)
    engine = create_db_engine(settings)
    OutboxEvent.__table__.create(engine, checkfirst=True)
    session_factory = create_session_factory(engine)

    results: list[HistoryBenchmarkResult] = []
    run_id = "benchmark"
    asset_id_prefix = "fuel-cell-stack-bench"

    print(f"database_url={args.database_url}")
    print(f"history_sizes={history_sizes}")
    print(f"benchmark_jobs={args.benchmark_jobs}")
    print(f"presentation_ingest_jobs_per_s={PRESENTATION_INGEST_JOBS_PER_SEC:.2f}")
    print(f"realistic_ingest_jobs_per_s={REALISTIC_INGEST_JOBS_PER_SEC:.2f}")
    print()

    try:
        for history_size in history_sizes:
            asset_id = f"{asset_id_prefix}-{history_size}"
            result = benchmark_history_size(
                session_factory=session_factory,
                history_size=history_size,
                benchmark_jobs=args.benchmark_jobs,
                asset_id=asset_id,
                run_id=run_id,
            )
            results.append(result)
            print(
                f"history={history_size:5d}  "
                f"avg_job={result.avg_job_seconds:.3f}s  "
                f"p95_job={result.p95_job_seconds:.3f}s  "
                f"throughput={result.throughput_jobs_per_second:.2f} jobs/s  "
                f"list_by_asset={result.avg_list_by_asset_seconds * 1000:.1f}ms  "
                f"presentation_growth="
                f"{result.presentation_queue_growth_per_min:+.1f}/min  "
                f"realistic_growth={result.realistic_queue_growth_per_min:+.1f}/min"
            )
    finally:
        # Never leave benchmark assets inside the demo database.
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            for history_size in history_sizes:
                _reset_asset_data(uow.session, f"{asset_id_prefix}-{history_size}")
        print("\nbenchmark_assets_cleaned=true")
        engine.dispose()

    payload = {
        "presentation_ingest_jobs_per_second": PRESENTATION_INGEST_JOBS_PER_SEC,
        "realistic_ingest_jobs_per_second": REALISTIC_INGEST_JOBS_PER_SEC,
        "results": [asdict(result) for result in results],
    }
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print(f"\nWrote {args.output}")

    realistic_ok = all(result.realistic_bounded for result in results)
    presentation_ok = all(result.presentation_bounded for result in results)
    print()
    print(f"presentation_mode_bounded={presentation_ok}")
    print(f"realistic_mode_bounded={realistic_ok}")

    return 0 if presentation_ok else 1


if __name__ == "__main__":
    sys.exit(main())

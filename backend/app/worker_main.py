"""Entry point for the reasoning worker process."""

from __future__ import annotations

import signal
import time

from sqlalchemy.orm import Session, sessionmaker

from backend.app.application.bootstrap import (
    ApplicationRuntime,
    bootstrap_application_runtime,
)
from backend.app.application.reasoning_job_queue import DatabaseReasoningJobQueue
from backend.app.application.reasoning_worker import ReasoningWorker
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.application.worker_heartbeat_service import WorkerHeartbeatService
from backend.app.infrastructure.config.settings import get_settings
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.logging import configure_logging, get_logger
from backend.app.infrastructure.persistence.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from backend.app.infrastructure.repositories.reasoning_job_repository import (
    SqlAlchemyReasoningJobRepository,
)
from backend.app.infrastructure.tracing import configure_tracing, shutdown_tracing
from backend.app.infrastructure.worker.worker_identity import build_worker_id

logger = get_logger(__name__)

_shutdown_requested = False


def _handle_shutdown(signum: int, _frame: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("worker_shutdown_requested", signal=signum)


def _database_queue_factory(uow: UnitOfWork[Session]) -> DatabaseReasoningJobQueue:
    return DatabaseReasoningJobQueue(SqlAlchemyReasoningJobRepository(uow.session))


def create_reasoning_worker(
    session_factory: sessionmaker[Session],
    application_runtime: ApplicationRuntime,
) -> ReasoningWorker:
    """Build a worker wired to the database-backed job queue."""
    if application_runtime.outbox_dispatcher is None:
        msg = "outbox dispatcher is required to run the reasoning worker"
        raise RuntimeError(msg)

    return ReasoningWorker(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        _database_queue_factory,
        application_runtime.domain_event_bus,
        application_runtime.outbox_dispatcher,
    )


def run_worker(*, poll_interval_seconds: float = 1.0) -> None:
    """Poll the database queue and process reasoning jobs until shutdown."""
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        environment=settings.environment,
    )
    configure_tracing(
        settings,
        service_name=settings.otel_service_name or "odis-worker",
    )

    if settings.database_url is None:
        msg = "DATABASE_URL is required to run the reasoning worker"
        raise RuntimeError(msg)

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    application_runtime = bootstrap_application_runtime(
        settings,
        unit_of_work_factory=lambda: SqlAlchemyUnitOfWork(session_factory),
    )

    worker = create_reasoning_worker(session_factory, application_runtime)
    if application_runtime.forecast_inference_engine is not None:
        logger.info(
            "forecast_inference_engine_ready",
            model_id=application_runtime.forecast_inference_engine.model_spec.model_id,
        )
    heartbeat_service = WorkerHeartbeatService(
        lambda: SqlAlchemyUnitOfWork(session_factory),
        worker_id=build_worker_id(),
    )
    heartbeat_interval = settings.worker_heartbeat_interval_seconds
    last_heartbeat_at = 0.0

    logger.info("reasoning_worker_started", poll_interval_seconds=poll_interval_seconds)
    try:
        while not _shutdown_requested:
            now_mono = time.monotonic()
            if now_mono - last_heartbeat_at >= heartbeat_interval:
                heartbeat_service.record_heartbeat()
                last_heartbeat_at = now_mono

            processed = worker.process_next()
            if not processed:
                time.sleep(poll_interval_seconds)
    finally:
        engine.dispose()
        shutdown_tracing()
        logger.info("reasoning_worker_stopped")


def main() -> None:
    """CLI entry point for the reasoning worker."""
    run_worker()


if __name__ == "__main__":
    main()

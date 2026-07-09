"""Worker orchestration for asynchronous reasoning execution."""

import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.observation_service_factory import (
    create_observation_service,
)
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.reasoning_job_queue import ReasoningJobQueue
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics.reasoning_metrics import (
    record_reasoning_failure,
    record_reasoning_run,
)
from backend.app.infrastructure.metrics.worker_metrics import (
    record_reasoning_job_duration,
)
from backend.app.infrastructure.tracing import business_span

logger = get_logger(__name__)


class ReasoningWorker:
    """Claim and execute reasoning jobs without implementing reasoning logic."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork[Session]],
        job_queue_factory: Callable[[UnitOfWork[Session]], ReasoningJobQueue],
        event_bus: DomainEventBus,
        outbox_dispatcher: OutboxDispatcher,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._job_queue_factory = job_queue_factory
        self._event_bus = event_bus
        self._outbox_dispatcher = outbox_dispatcher

    def process_next(self) -> bool:
        """Claim and process the next pending job. Returns True when a job ran."""
        with self._unit_of_work_factory() as uow:
            job_queue = self._job_queue_factory(uow)
            job = job_queue.claim()
            if job is None:
                return False

            start = time.perf_counter()
            try:
                with business_span(
                    "process_reasoning_job",
                    attributes={"job_id": job.id, "asset_id": job.asset_id},
                ):
                    service = create_observation_service(
                        uow,
                        self._event_bus,
                        self._outbox_dispatcher,
                    )
                    service.run_reasoning_for_asset(job.asset_id)
                    job_queue.complete(job)
                    uow.commit()
                    self._outbox_dispatcher.dispatch()
                record_reasoning_run()
                record_reasoning_job_duration(time.perf_counter() - start)
                logger.info(
                    "reasoning_job_completed",
                    job_id=job.id,
                    asset_id=job.asset_id,
                    attempts=job.attempts,
                )
                return True
            except Exception:
                job_queue.fail(job)
                uow.commit()
                record_reasoning_failure()
                logger.exception(
                    "reasoning_job_failed",
                    job_id=job.id,
                    asset_id=job.asset_id,
                    attempts=job.attempts,
                )
                raise

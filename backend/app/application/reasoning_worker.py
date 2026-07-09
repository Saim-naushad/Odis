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
    reasoning_duration_seconds,
    reasoning_failures_total,
    reasoning_runs_total,
)

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
                service = create_observation_service(
                    uow,
                    self._event_bus,
                    self._outbox_dispatcher,
                )
                service.run_reasoning_for_asset(job.asset_id)
                job_queue.complete(job)
                uow.commit()
                self._outbox_dispatcher.dispatch()
                reasoning_runs_total.inc()
                reasoning_duration_seconds.observe(time.perf_counter() - start)
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
                reasoning_failures_total.inc()
                logger.exception(
                    "reasoning_job_failed",
                    job_id=job.id,
                    asset_id=job.asset_id,
                    attempts=job.attempts,
                )
                raise

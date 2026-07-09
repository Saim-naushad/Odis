"""In-process background execution for post-observation reasoning."""

import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.observation_service_factory import (
    create_observation_service,
)
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.infrastructure.logging import (
    bind_request_id,
    clear_log_context,
    get_logger,
)
from backend.app.infrastructure.metrics.reasoning_metrics import (
    reasoning_duration_seconds,
    reasoning_failures_total,
    reasoning_runs_total,
)

logger = get_logger(__name__)


class ReasoningTaskRunner:
    """Run reasoning in a dedicated database session after observations persist."""

    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork[Session]],
        event_bus: DomainEventBus,
        outbox_dispatcher: OutboxDispatcher,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._event_bus = event_bus
        self._outbox_dispatcher = outbox_dispatcher

    def run_for_asset(self, asset_id: str, request_id: str | None = None) -> None:
        """Execute reasoning for an asset using a fresh database session.

        ``request_id`` is captured when the task is scheduled because request
        middleware clears logging context before FastAPI background tasks run.
        """
        bind_request_id(request_id)
        start = time.perf_counter()
        try:
            with self._unit_of_work_factory() as uow:
                service = create_observation_service(
                    uow,
                    self._event_bus,
                    self._outbox_dispatcher,
                )
                ran = service.run_reasoning_for_asset(asset_id)
                uow.commit()
                self._outbox_dispatcher.dispatch()
                if ran:
                    reasoning_runs_total.inc()
                    reasoning_duration_seconds.observe(time.perf_counter() - start)
        except Exception:
            reasoning_failures_total.inc()
            logger.exception(
                "background_reasoning_failed",
                asset_id=asset_id,
            )
            raise
        finally:
            clear_log_context()

"""In-process background execution for post-observation reasoning."""

from sqlalchemy.orm import Session, sessionmaker

from backend.app.application.monitoring_event_source import MonitoringEventSource
from backend.app.application.observation_service_factory import (
    create_observation_service,
)
from backend.app.infrastructure.logging import (
    bind_request_id,
    clear_log_context,
    get_logger,
)

logger = get_logger(__name__)


class ReasoningTaskRunner:
    """Run reasoning in a dedicated database session after observations persist."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        monitoring_event_source: MonitoringEventSource,
    ) -> None:
        self._session_factory = session_factory
        self._monitoring_event_source = monitoring_event_source

    def run_for_asset(self, asset_id: str, request_id: str | None = None) -> None:
        """Execute reasoning for an asset using a fresh database session.

        ``request_id`` is captured when the task is scheduled because request
        middleware clears logging context before FastAPI background tasks run.
        """
        bind_request_id(request_id)
        session = self._session_factory()
        try:
            service = create_observation_service(session, self._monitoring_event_source)
            service.run_reasoning_for_asset(asset_id)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception(
                "background_reasoning_failed",
                asset_id=asset_id,
            )
            raise
        finally:
            session.close()
            clear_log_context()

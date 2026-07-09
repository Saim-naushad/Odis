"""In-process background execution for post-observation reasoning."""

import logging

from sqlalchemy.orm import Session, sessionmaker

from backend.app.application.monitoring_event_source import MonitoringEventSource
from backend.app.application.observation_service_factory import (
    create_observation_service,
)

logger = logging.getLogger(__name__)


class ReasoningTaskRunner:
    """Run reasoning in a dedicated database session after observations persist."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        monitoring_event_source: MonitoringEventSource,
    ) -> None:
        self._session_factory = session_factory
        self._monitoring_event_source = monitoring_event_source

    def run_for_asset(self, asset_id: str) -> None:
        """Execute reasoning for an asset using a fresh database session."""
        session = self._session_factory()
        try:
            service = create_observation_service(session, self._monitoring_event_source)
            service.run_reasoning_for_asset(asset_id)
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("Background reasoning failed for asset %s", asset_id)
            raise
        finally:
            session.close()

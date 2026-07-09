"""Application service for observation persistence and reasoning orchestration."""

from collections.abc import Sequence
from datetime import UTC, datetime

from application.reasoning_session import ReasoningSession
from application.reasoning_trace_repository import ReasoningTraceRepository
from application.structured_assessment_repository import StructuredAssessmentRepository
from backend.app.application.events.domain_events import (
    ObservationCreated,
    ReasoningCompleted,
)
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.exceptions import ObservationAlreadyExistsError
from backend.app.application.reasoning_config import DEFAULT_OPERATIONAL_GOAL
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics.observation_metrics import (
    observations_created_total,
)
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.repositories.observation_repository import ObservationRepository

logger = get_logger(__name__)


def _can_run_reasoning(observations: Sequence[Observation]) -> bool:
    if len(observations) < 2:
        return False
    primary_measurement_type = observations[0].measurement_type
    primary_count = sum(
        1
        for observation in observations
        if observation.measurement_type == primary_measurement_type
    )
    return primary_count >= 2


class ObservationService:
    """Coordinate observation persistence and automatic reasoning."""

    def __init__(
        self,
        repository: ObservationRepository,
        *,
        event_bus: DomainEventBus | None = None,
        reasoning_session: ReasoningSession | None = None,
        structured_assessment_repository: StructuredAssessmentRepository | None = None,
        reasoning_trace_repository: ReasoningTraceRepository | None = None,
        operational_goal: OperationalGoal | None = None,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus
        self._reasoning_session = reasoning_session
        self._structured_assessment_repository = structured_assessment_repository
        self._reasoning_trace_repository = reasoning_trace_repository
        self._operational_goal = operational_goal or DEFAULT_OPERATIONAL_GOAL

    def create(self, observation: Observation) -> Observation:
        """Persist a new observation."""
        try:
            self._repository.save(observation)
        except ValueError as exc:
            if "already exists" in str(exc):
                raise ObservationAlreadyExistsError(str(exc)) from exc
            raise

        if self._event_bus is not None:
            self._event_bus.publish(
                ObservationCreated(
                    asset_id=observation.asset_id,
                    observation_id=observation.id,
                    timestamp=datetime.now(UTC),
                )
            )
        observations_created_total.inc()
        logger.info(
            "observation_created",
            observation_id=observation.id,
            asset_id=observation.asset_id,
        )
        return observation

    def get(self, observation_id: str) -> Observation | None:
        """Return a persisted observation when it exists."""
        return self._repository.get(observation_id)

    def list_observations(self) -> list[Observation]:
        """Return all persisted observations in deterministic order."""
        return self._repository.list()

    def run_reasoning_for_asset(self, asset_id: str) -> bool:
        if self._reasoning_session is None:
            return False

        asset_observations = self._repository.list_by_asset(asset_id)
        if not _can_run_reasoning(asset_observations):
            return False

        result = self._reasoning_session.run(
            self._operational_goal,
            asset_observations,
        )

        if self._structured_assessment_repository is not None:
            self._structured_assessment_repository.save(
                result.run.id,
                result.structured_assessment,
            )
        if self._reasoning_trace_repository is not None:
            self._reasoning_trace_repository.save(result.run.id, result.trace)

        if self._event_bus is not None:
            self._event_bus.publish(
                ReasoningCompleted(
                    asset_id=asset_id,
                    run_id=result.run.id,
                    timestamp=datetime.now(UTC),
                )
            )
        logger.info(
            "reasoning_completed",
            asset_id=asset_id,
            run_id=result.run.id,
        )
        return True

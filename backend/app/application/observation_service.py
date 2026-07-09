"""Application service for observation persistence and reasoning orchestration."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from application.reasoning_run_index import ReasoningRunIndexRepository
from application.reasoning_session import ReasoningSession
from application.reasoning_trace_repository import ReasoningTraceRepository
from application.structured_assessment_repository import StructuredAssessmentRepository
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.exceptions import ObservationAlreadyExistsError
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.reasoning_config import DEFAULT_OPERATIONAL_GOAL
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.outbox import OutboxEvent
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics.observation_metrics import (
    observations_created_total,
)
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.reasoning_run_repository import ReasoningRunRepository

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
        uow: UnitOfWork[Any],
        repository: ObservationRepository,
        *,
        event_bus: DomainEventBus | None = None,
        outbox_dispatcher: OutboxDispatcher | None = None,
        reasoning_session: ReasoningSession | None = None,
        structured_assessment_repository: StructuredAssessmentRepository | None = None,
        reasoning_trace_repository: ReasoningTraceRepository | None = None,
        decision_plan_repository: DecisionPlanRepository | None = None,
        reasoning_run_index_repository: ReasoningRunIndexRepository | None = None,
        reasoning_run_repository: ReasoningRunRepository | None = None,
        operational_goal: OperationalGoal | None = None,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._event_bus = event_bus
        self._outbox_dispatcher = outbox_dispatcher
        self._reasoning_session = reasoning_session
        self._structured_assessment_repository = structured_assessment_repository
        self._reasoning_trace_repository = reasoning_trace_repository
        self._decision_plan_repository = decision_plan_repository
        self._reasoning_run_index_repository = reasoning_run_index_repository
        self._reasoning_run_repository = reasoning_run_repository
        self._operational_goal = operational_goal or DEFAULT_OPERATIONAL_GOAL

    def create(self, observation: Observation) -> Observation:
        """Persist a new observation."""
        try:
            self._repository.save(observation)
            if self._event_bus is not None:
                outbox_event = OutboxEvent(
                    id=str(uuid4()),
                    event_type="ObservationCreated",
                    payload={
                        "asset_id": observation.asset_id,
                        "observation_id": observation.id,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    created_at=datetime.now(UTC),
                    dispatched_at=None,
                )
                self._uow.session.add(outbox_event)
            self._uow.commit()
        except ValueError as exc:
            if "already exists" in str(exc):
                raise ObservationAlreadyExistsError(str(exc)) from exc
            raise

        if self._event_bus is not None and self._outbox_dispatcher is not None:
            self._outbox_dispatcher.dispatch()
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

        previous_recommendation = self._latest_recommendation_for_asset(asset_id)
        now = datetime.now(UTC)

        result = self._reasoning_session.run(
            self._operational_goal,
            asset_observations,
        )

        if self._event_bus is not None:
            started_event = OutboxEvent(
                id=str(uuid4()),
                event_type="ReasoningStarted",
                payload={
                    "asset_id": asset_id,
                    "run_id": result.run.id,
                    "timestamp": result.run.started_at.isoformat(),
                },
                created_at=now,
                dispatched_at=None,
            )
            self._uow.session.add(started_event)

        if self._structured_assessment_repository is not None:
            self._structured_assessment_repository.save(
                result.run.id,
                result.structured_assessment,
            )
        if self._reasoning_trace_repository is not None:
            self._reasoning_trace_repository.save(result.run.id, result.trace)

        if self._event_bus is not None:
            if (
                previous_recommendation is not None
                and previous_recommendation != result.plan.recommendation
            ):
                recommendation_event = OutboxEvent(
                    id=str(uuid4()),
                    event_type="RecommendationUpdated",
                    payload={
                        "asset_id": asset_id,
                        "run_id": result.run.id,
                        "previous_recommendation": previous_recommendation,
                        "new_recommendation": result.plan.recommendation,
                        "timestamp": now.isoformat(),
                    },
                    created_at=now,
                    dispatched_at=None,
                )
                self._uow.session.add(recommendation_event)

            outbox_event = OutboxEvent(
                id=str(uuid4()),
                event_type="ReasoningCompleted",
                payload={
                    "asset_id": asset_id,
                    "run_id": result.run.id,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                created_at=datetime.now(UTC),
                dispatched_at=None,
            )
            self._uow.session.add(outbox_event)
        logger.info(
            "reasoning_completed",
            asset_id=asset_id,
            run_id=result.run.id,
        )
        return True

    def _latest_recommendation_for_asset(self, asset_id: str) -> str | None:
        if (
            self._decision_plan_repository is None
            or self._reasoning_run_index_repository is None
            or self._reasoning_run_repository is None
        ):
            return None

        asset_observation_ids = {
            observation.id
            for observation in self._repository.list_by_asset(asset_id)
        }
        latest_plan_id: str | None = None
        latest_started_at: datetime | None = None
        for index in self._reasoning_run_index_repository.list():
            if not any(
                observation_id in asset_observation_ids
                for observation_id in index.observation_ids
            ):
                continue
            run = self._reasoning_run_repository.get(index.run_id)
            if run is None:
                continue
            if latest_started_at is None or run.started_at > latest_started_at:
                latest_started_at = run.started_at
                latest_plan_id = index.plan_id

        if latest_plan_id is None:
            return None
        plan = self._decision_plan_repository.get(latest_plan_id)
        return plan.recommendation if plan is not None else None

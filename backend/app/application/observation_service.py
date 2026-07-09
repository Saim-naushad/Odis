"""Application service for observation persistence and reasoning orchestration."""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from application.reasoning_run_index import ReasoningRunIndexRepository
from application.reasoning_session import ReasoningSession
from application.reasoning_trace_repository import ReasoningTraceRepository
from application.structured_assessment_repository import StructuredAssessmentRepository
from backend.app.application.events.event_bus import DomainEventBus
from backend.app.application.exceptions import ObservationAlreadyExistsError
from backend.app.application.notification_policy_engine import NotificationPolicyEngine
from backend.app.application.operational_state_engine import OperationalStateEngine
from backend.app.application.outbox_dispatcher import OutboxDispatcher
from backend.app.application.reasoning_config import DEFAULT_OPERATIONAL_GOAL
from backend.app.application.reasoning_job_queue import ReasoningJobQueue
from backend.app.application.recommendation_engine import RecommendationEngine
from backend.app.application.time_series_analysis import analyze_trend_diagnostics
from backend.app.application.unit_of_work import UnitOfWork
from backend.app.domain.operational_state import OperationalState
from backend.app.domain.outbox import OutboxEvent
from backend.app.domain.reasoning_job import ReasoningJob
from backend.app.domain.recommendation import Recommendation
from backend.app.infrastructure.logging import get_logger
from backend.app.infrastructure.metrics.notification_metrics import (
    record_notification_created,
)
from backend.app.infrastructure.metrics.observation_metrics import (
    record_observation_created,
)
from backend.app.infrastructure.metrics.operational_state_metrics import (
    record_operational_state_transition,
)
from backend.app.infrastructure.metrics.reasoning_metrics import (
    record_reasoning_duration,
    record_trend_analysis_duration,
)
from backend.app.infrastructure.metrics.recommendation_metrics import (
    record_recommendation_computed,
)
from backend.app.infrastructure.tracing import business_span
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.reasoning_run_repository import ReasoningRunRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ObservationCreateResult:
    """Result of persisting an observation and enqueueing reasoning."""

    observation: Observation
    job: ReasoningJob | None


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
        reasoning_job_queue: ReasoningJobQueue | None = None,
    ) -> None:
        self._uow = uow
        self._repository = repository
        self._event_bus = event_bus
        self._outbox_dispatcher = outbox_dispatcher
        self._reasoning_job_queue = reasoning_job_queue
        self._reasoning_session = reasoning_session
        self._structured_assessment_repository = structured_assessment_repository
        self._reasoning_trace_repository = reasoning_trace_repository
        self._decision_plan_repository = decision_plan_repository
        self._reasoning_run_index_repository = reasoning_run_index_repository
        self._reasoning_run_repository = reasoning_run_repository
        self._operational_goal = operational_goal or DEFAULT_OPERATIONAL_GOAL

    def create(self, observation: Observation) -> ObservationCreateResult:
        """Persist a new observation and enqueue asynchronous reasoning."""
        job: ReasoningJob | None = None
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
            if self._reasoning_job_queue is not None:
                job = self._reasoning_job_queue.enqueue(observation.asset_id)
            self._uow.commit()
        except ValueError as exc:
            if "already exists" in str(exc):
                raise ObservationAlreadyExistsError(str(exc)) from exc
            raise

        if self._event_bus is not None and self._outbox_dispatcher is not None:
            self._outbox_dispatcher.dispatch()
        record_observation_created()
        logger.info(
            "observation_created",
            observation_id=observation.id,
            asset_id=observation.asset_id,
            job_id=job.id if job is not None else None,
        )
        return ObservationCreateResult(observation=observation, job=job)

    def get(self, observation_id: str) -> Observation | None:
        """Return a persisted observation when it exists."""
        return self._repository.get(observation_id)

    def list_observations(self) -> list[Observation]:
        """Return all persisted observations in deterministic order."""
        return self._repository.list()

    def run_reasoning_for_asset(self, asset_id: str) -> bool:
        if self._reasoning_session is None:
            return False

        with business_span("run_reasoning_pipeline", attributes={"asset_id": asset_id}):
            return self._run_reasoning_for_asset(asset_id)

    def _run_reasoning_for_asset(self, asset_id: str) -> bool:
        assert self._reasoning_session is not None

        asset_observations = self._repository.list_by_asset(asset_id)
        if not _can_run_reasoning(asset_observations):
            return False

        asset_observations = sorted(
            asset_observations, key=lambda obs: (obs.timestamp, obs.id)
        )
        previous_recommendation = self._latest_recommendation_for_asset(asset_id)
        previous_state = self._latest_operational_state_for_asset(asset_id)
        previous_notification_id: str | None = None
        if previous_state is not None:
            previous_notification_id = self._latest_notification_id_for_state(
                previous_state
            )
        now = datetime.now(UTC)

        primary_measurement_type = asset_observations[0].measurement_type
        primary_observations = [
            obs
            for obs in asset_observations
            if obs.measurement_type == primary_measurement_type
        ]
        previous_primary = (
            primary_observations[:-1] if len(primary_observations) >= 2 else []
        )
        trend_start = time.perf_counter()
        prev_trend = analyze_trend_diagnostics(
            previous_primary,
            observation_window=5,
        )
        record_trend_analysis_duration(time.perf_counter() - trend_start)

        reasoning_start = time.perf_counter()
        result = self._reasoning_session.run(
            self._operational_goal,
            asset_observations,
        )
        record_reasoning_duration(time.perf_counter() - reasoning_start)

        new_state: OperationalState | None = None
        notification = None
        if self._event_bus is not None and hasattr(result.plan, "priority"):
            new_state = self._compute_operational_state_from_result(
                asset_id=asset_id,
                result=result,
                observations=asset_observations,
            )
            recommendation = self._compute_recommendation_from_state(new_state)
            record_recommendation_computed(
                category=recommendation.category,
                priority=recommendation.priority,
                urgency=recommendation.urgency,
            )
            notification = NotificationPolicyEngine().compute(recommendation)

        trend_start = time.perf_counter()
        new_trend = analyze_trend_diagnostics(
            primary_observations,
            observation_window=5,
        )
        record_trend_analysis_duration(time.perf_counter() - trend_start)

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
                prev_trend is not None
                and new_trend is not None
                and prev_trend.direction != new_trend.direction
                and len(primary_observations) >= 4
                and new_trend.stability_score >= 70
                and new_trend.direction != "stable"
            ):
                trend_event = OutboxEvent(
                    id=str(uuid4()),
                    event_type="TrendChanged",
                    payload={
                        "asset_id": asset_id,
                        "run_id": result.run.id,
                        "previous_direction": prev_trend.direction,
                        "new_direction": new_trend.direction,
                        "stability_score": new_trend.stability_score,
                        "volatility_score": new_trend.volatility_score,
                        "timestamp": now.isoformat(),
                    },
                    created_at=now,
                    dispatched_at=None,
                )
                self._uow.session.add(trend_event)
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

            if previous_state is not None:
                # Operational State transitions (meaningful only).
                if new_state is None:
                    new_state = self._compute_operational_state_from_result(
                        asset_id=asset_id,
                        result=result,
                        observations=asset_observations,
                    )
                if previous_state.health_status != new_state.health_status:
                    record_operational_state_transition(
                        from_state=previous_state.health_status,
                        to_state=new_state.health_status,
                    )
                    self._uow.session.add(
                        OutboxEvent(
                            id=str(uuid4()),
                            event_type="HealthChanged",
                            payload={
                                "asset_id": asset_id,
                                "run_id": result.run.id,
                                "previous_health_status": previous_state.health_status,
                                "new_health_status": new_state.health_status,
                                "health_score": new_state.health_score,
                                "timestamp": now.isoformat(),
                            },
                            created_at=now,
                            dispatched_at=None,
                        )
                    )
                if previous_state.risk_level != new_state.risk_level:
                    record_operational_state_transition(
                        from_state=previous_state.risk_level,
                        to_state=new_state.risk_level,
                    )
                    self._uow.session.add(
                        OutboxEvent(
                            id=str(uuid4()),
                            event_type="RiskChanged",
                            payload={
                                "asset_id": asset_id,
                                "run_id": result.run.id,
                                "previous_risk_level": previous_state.risk_level,
                                "new_risk_level": new_state.risk_level,
                                "health_score": new_state.health_score,
                                "timestamp": now.isoformat(),
                            },
                            created_at=now,
                            dispatched_at=None,
                        )
                    )

            if (
                notification is not None
                and previous_notification_id != notification.id
            ):
                record_notification_created(
                    severity=notification.severity,
                    status=notification.status,
                )
                self._uow.session.add(
                    OutboxEvent(
                        id=str(uuid4()),
                        event_type="NotificationCreated",
                        payload={
                            "asset_id": asset_id,
                            "run_id": result.run.id,
                            "notification_id": notification.id,
                            "recommendation_id": notification.recommendation_id,
                            "severity": notification.severity,
                            "status": notification.status,
                            "title": notification.title,
                            "message": notification.message,
                            "created_at": notification.created_at.isoformat(),
                            "timestamp": now.isoformat(),
                        },
                        created_at=now,
                        dispatched_at=None,
                    )
                )

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

    def _compute_recommendation_from_state(
        self, state: OperationalState
    ) -> Recommendation:
        return RecommendationEngine().compute(state)

    def _latest_notification_id_for_state(self, state: OperationalState) -> str | None:
        recommendation = self._compute_recommendation_from_state(state)
        notification = NotificationPolicyEngine().compute(recommendation)
        return notification.id if notification is not None else None

    def _compute_operational_state_from_result(
        self,
        *,
        asset_id: str,
        result: Any,
        observations: list[Observation],
    ) -> OperationalState:
        # ReasoningResult is defined in src/application; we keep this method typed
        # loosely to avoid coupling backend service signatures to that module.
        assessment = str(getattr(getattr(result, "context", None), "assessment", ""))
        structured_assessment = getattr(result, "structured_assessment", None)
        decision_plan = result.plan
        run = result.run
        engine = OperationalStateEngine()
        return engine.compute(
            asset_id=asset_id,
            last_updated=run.started_at,
            assessment=assessment,
            observations=observations,
            decision_plan=decision_plan,
            structured_assessment=structured_assessment,
        )

    def _latest_operational_state_for_asset(
        self, asset_id: str
    ) -> OperationalState | None:
        if (
            self._decision_plan_repository is None
            or self._reasoning_run_index_repository is None
            or self._reasoning_run_repository is None
        ):
            return None

        latest_run_id = self._latest_run_id_for_asset(asset_id)
        if latest_run_id is None:
            return None
        return self._compute_operational_state_for_run(
            asset_id=asset_id,
            run_id=latest_run_id,
        )

    def _latest_run_id_for_asset(self, asset_id: str) -> str | None:
        if (
            self._reasoning_run_index_repository is None
            or self._reasoning_run_repository is None
        ):
            return None

        asset_observation_ids = {
            observation.id for observation in self._repository.list_by_asset(asset_id)
        }
        latest_run_id: str | None = None
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
                latest_run_id = index.run_id
        return latest_run_id

    def _compute_operational_state_for_run(
        self,
        *,
        asset_id: str,
        run_id: str,
    ) -> OperationalState | None:
        if (
            self._decision_plan_repository is None
            or self._reasoning_run_index_repository is None
            or self._reasoning_run_repository is None
        ):
            return None

        index = self._reasoning_run_index_repository.get(run_id)
        run = self._reasoning_run_repository.get(run_id)
        if index is None or run is None:
            return None

        plan = self._decision_plan_repository.get(index.plan_id)
        if plan is None:
            return None

        observations: list[Observation] = []
        for observation_id in index.observation_ids:
            obs = self._repository.get(observation_id)
            if obs is not None:
                observations.append(obs)
        observations.sort(key=lambda obs: (obs.timestamp, obs.id))

        structured_assessment = (
            self._structured_assessment_repository.get_by_run_id(run_id)
            if self._structured_assessment_repository is not None
            else None
        )

        engine = OperationalStateEngine()
        return engine.compute(
            asset_id=asset_id,
            last_updated=run.started_at,
            assessment="",
            observations=observations,
            decision_plan=plan,
            structured_assessment=structured_assessment,
        )

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

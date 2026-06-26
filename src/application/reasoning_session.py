from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from application.create_decision_context import create_decision_context
from application.decision_planner import DecisionPlanner
from application.event_publisher import EventPublisher
from application.operational_situation_assessor import OperationalSituationAssessor
from application.reasoning_run import ReasoningRun
from application.record_action import record_action
from application.record_outcome import record_outcome
from application.trend_detector import TrendDetector
from application.variation_detector import VariationDetector
from domain.entities.action import Action
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.entities.operational_situation import OperationalSituation
from domain.entities.outcome import Outcome
from domain.events.decision_context_created import DecisionContextCreated
from domain.events.decision_plan_generated import DecisionPlanGenerated
from domain.events.observation_recorded import ObservationRecorded
from domain.events.operational_situation_created import OperationalSituationCreated
from domain.repositories.decision_context_repository import DecisionContextRepository
from domain.repositories.decision_plan_repository import DecisionPlanRepository
from domain.repositories.observation_repository import ObservationRepository
from domain.repositories.situation_repository import SituationRepository
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation


@dataclass(frozen=True)
class ReasoningResult:
    run: ReasoningRun
    trend: DetectedTrend
    variation: DetectedVariation
    situation: OperationalSituation
    context: DecisionContext
    plan: DecisionPlan
    action: Action
    outcome: Outcome


class ReasoningSession:
    def __init__(
        self,
        observation_repository: ObservationRepository | None = None,
        situation_repository: SituationRepository | None = None,
        decision_context_repository: DecisionContextRepository | None = None,
        decision_plan_repository: DecisionPlanRepository | None = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._observation_repository = observation_repository
        self._situation_repository = situation_repository
        self._decision_context_repository = decision_context_repository
        self._decision_plan_repository = decision_plan_repository
        self._event_publisher = event_publisher

    def run(
        self,
        goal: OperationalGoal,
        observations: Sequence[Observation],
    ) -> ReasoningResult:
        run = ReasoningRun(
            id=str(uuid4()),
            started_at=datetime.now(UTC),
        )

        for observation in observations:
            if self._event_publisher is not None:
                self._event_publisher.publish(
                    ObservationRecorded(
                        observation_id=observation.id,
                        recorded_at=observation.timestamp,
                    )
                )
            if self._observation_repository is not None:
                self._observation_repository.save(observation)

        trend = TrendDetector().detect(observations)
        variation = VariationDetector().detect(observations)
        situation = OperationalSituationAssessor().assess(
            goal, observations, trend, variation
        )

        if self._event_publisher is not None:
            self._event_publisher.publish(
                OperationalSituationCreated(
                    situation_id=situation.id,
                    created_at=datetime.now(UTC),
                )
            )
        if self._situation_repository is not None:
            self._situation_repository.save(situation)

        context = create_decision_context(goal, situation)

        if self._event_publisher is not None:
            self._event_publisher.publish(
                DecisionContextCreated(
                    context_id=context.id,
                    created_at=context.created_at,
                )
            )
        if self._decision_context_repository is not None:
            self._decision_context_repository.save(context)

        plan = DecisionPlanner().plan(context)

        if self._event_publisher is not None:
            self._event_publisher.publish(
                DecisionPlanGenerated(
                    plan_id=plan.id,
                    generated_at=plan.created_at,
                )
            )
        if self._decision_plan_repository is not None:
            self._decision_plan_repository.save(plan)

        action = record_action(plan)
        outcome = record_outcome(action)
        # Action and outcome persistence will follow once repository contracts exist.

        return ReasoningResult(
            run=run,
            trend=trend,
            variation=variation,
            situation=situation,
            context=context,
            plan=plan,
            action=action,
            outcome=outcome,
        )

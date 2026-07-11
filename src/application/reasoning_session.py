from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from application.event_publisher import EventPublisher
from application.expectation_analysis import ExpectationAnalysis
from application.observation_source import ObservationSource
from application.operational_context import OperationalContext
from application.operational_profile import OperationalProfile
from application.planning_context import PlanningContext
from application.reasoning.assessment_stage import AssessmentStage
from application.reasoning.confidence_stage import ConfidenceStage
from application.reasoning.context import ReasoningContext
from application.reasoning.evidence_generation_stage import EvidenceGenerationStage
from application.reasoning.explanation_stage import ExplanationStage
from application.reasoning.hypothesis_stage import HypothesisStage
from application.reasoning.planning_stage import PlanningStage
from application.reasoning.signal_extraction_stage import SignalExtractionStage
from application.reasoning.stage import ReasoningStage
from application.reasoning_run import ReasoningRun
from application.reasoning_run_index import (
    ReasoningRunIndex,
    ReasoningRunIndexRepository,
)
from application.reasoning_run_registry import (
    ReasoningRunRegistryEntry,
    ReasoningRunRegistryRepository,
)
from application.reasoning_trace import ReasoningTrace, TraceStep
from application.record_action import record_action
from application.record_outcome import record_outcome
from application.structured_assessment import StructuredAssessment
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
from domain.repositories.reasoning_run_repository import ReasoningRunRepository
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
    trace: ReasoningTrace
    operational_context: OperationalContext
    expectation_analysis: ExpectationAnalysis
    structured_assessment: StructuredAssessment
    planning_context: PlanningContext
    reasoning_context: ReasoningContext

class ReasoningSession:
    def __init__(
        self,
        profile: OperationalProfile | None = None,
        observation_repository: ObservationRepository | None = None,
        situation_repository: SituationRepository | None = None,
        decision_context_repository: DecisionContextRepository | None = None,
        decision_plan_repository: DecisionPlanRepository | None = None,
        reasoning_run_repository: ReasoningRunRepository | None = None,
        reasoning_run_index_repository: ReasoningRunIndexRepository | None = None,
        reasoning_run_registry_repository: (
            ReasoningRunRegistryRepository | None
        ) = None,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self._profile = profile or OperationalProfile.default()
        self._observation_repository = observation_repository
        self._situation_repository = situation_repository
        self._decision_context_repository = decision_context_repository
        self._decision_plan_repository = decision_plan_repository
        self._reasoning_run_repository = reasoning_run_repository
        self._reasoning_run_index_repository = reasoning_run_index_repository
        self._reasoning_run_registry_repository = reasoning_run_registry_repository
        self._event_publisher = event_publisher
        self._stages: tuple[ReasoningStage, ...] = (
            SignalExtractionStage(),
            EvidenceGenerationStage(),
            HypothesisStage(),
            AssessmentStage(),
            ConfidenceStage(),
            ExplanationStage(),
            PlanningStage(),
        )

    @property
    def stages(self) -> tuple[ReasoningStage, ...]:
        return self._stages

    def run(
        self,
        goal: OperationalGoal,
        observations: Sequence[Observation],
    ) -> ReasoningResult:
        run = ReasoningRun(
            id=str(uuid4()),
            started_at=datetime.now(UTC),
        )

        if self._reasoning_run_repository is not None:
            self._reasoning_run_repository.save(run)

        if self._reasoning_run_registry_repository is not None:
            self._reasoning_run_registry_repository.add(
                ReasoningRunRegistryEntry(
                    run_id=run.id,
                    started_at=run.started_at,
                )
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

        reasoning_context = ReasoningContext(
            goal=goal,
            observations=tuple(observations),
            profile=self._profile,
        ).with_metadata(run_id=run.id)
        for stage in self._stages:
            reasoning_context = stage.run(reasoning_context)

        artifacts = reasoning_context.artifacts
        signals = artifacts.signals
        assessment_summary = artifacts.assessment_summary
        structured_assessment = artifacts.structured_assessment
        planning_context = artifacts.planning_context
        context = artifacts.decision_context
        plan = artifacts.decision_plan
        if (
            signals is None
            or assessment_summary is None
            or assessment_summary.situation is None
            or structured_assessment is None
            or planning_context is None
            or context is None
            or plan is None
        ):
            raise RuntimeError(
                "explicit reasoning pipeline did not populate required artifacts"
            )

        trend = signals.trend
        variation = signals.variation
        situation = assessment_summary.situation
        operational_context = signals.operational_context
        expectation_analysis = signals.expectation_analysis

        if self._event_publisher is not None:
            self._event_publisher.publish(
                OperationalSituationCreated(
                    situation_id=situation.id,
                    created_at=datetime.now(UTC),
                )
            )
        if self._situation_repository is not None:
            self._situation_repository.save(situation)

        if self._event_publisher is not None:
            self._event_publisher.publish(
                DecisionContextCreated(
                    context_id=context.id,
                    created_at=context.created_at,
                )
            )
        if self._decision_context_repository is not None:
            self._decision_context_repository.save(context)

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

        if self._reasoning_run_index_repository is not None:
            asset_id = observations[0].asset_id if observations else ""
            self._reasoning_run_index_repository.save(
                ReasoningRunIndex(
                    run_id=run.id,
                    observation_ids=tuple(
                        observation.id for observation in observations
                    ),
                    situation_id=situation.id,
                    context_id=context.id,
                    plan_id=plan.id,
                    action_id=action.id,
                    outcome_id=outcome.id,
                    asset_id=asset_id,
                )
            )

        trace = ReasoningTrace(
            steps=(
                TraceStep(
                    name="Observations Loaded",
                    description="Incoming observations were received for reasoning.",
                ),
                TraceStep(
                    name="Signal Extraction",
                    description="Signals were extracted from incoming observations.",
                ),
                TraceStep(
                    name="Evidence Generation",
                    description="Structured evidence was generated from signals.",
                ),
                TraceStep(
                    name="Hypothesis Generation",
                    description="Candidate hypotheses were generated from evidence.",
                ),
                TraceStep(
                    name="Assessment",
                    description="Signals and hypotheses were assessed factually.",
                ),
                TraceStep(
                    name="Confidence",
                    description=(
                        "Confidence in the assessment was scored "
                        "deterministically."
                    ),
                ),
                TraceStep(
                    name="Explanation",
                    description=(
                        "A structured explanation was generated from artifacts."
                    ),
                ),
                TraceStep(
                    name="Planning",
                    description="The assessment was translated into a decision plan.",
                ),
                TraceStep(
                    name="Trend Detected",
                    description="A directional trend was derived from the readings.",
                ),
                TraceStep(
                    name="Variation Detected",
                    description="The variability of the observations was measured.",
                ),
                TraceStep(
                    name="Relationship Analysis",
                    description=(
                        "Cross-measurement correlations and contradictions "
                        "were evaluated."
                    ),
                ),
                TraceStep(
                    name="Operational Context Built",
                    description="The situational frame for reasoning was established.",
                ),
                TraceStep(
                    name="Expectations Evaluated",
                    description="Declared expectations were compared against evidence.",
                ),
                TraceStep(
                    name="Situation Assessed",
                    description="Signals and goal were combined into a situation.",
                ),
                TraceStep(
                    name="Decision Context Created",
                    description="A decision context snapshotted the planner inputs.",
                ),
                TraceStep(
                    name="Decision Planned",
                    description="A decision plan was produced from the context.",
                ),
                TraceStep(
                    name="Action Recorded",
                    description="An action was recorded from the decision plan.",
                ),
                TraceStep(
                    name="Outcome Recorded",
                    description="An outcome was recorded from the action.",
                ),
            )
        )

        return ReasoningResult(
            run=run,
            trend=trend,
            variation=variation,
            situation=situation,
            context=context,
            plan=plan,
            action=action,
            outcome=outcome,
            trace=trace,
            operational_context=operational_context,
            expectation_analysis=expectation_analysis,
            structured_assessment=structured_assessment,
            planning_context=planning_context,
            reasoning_context=reasoning_context,
        )

    def run_from_source(
        self,
        goal: OperationalGoal,
        source: ObservationSource,
    ) -> ReasoningResult:
        return self.run(goal, source.read())

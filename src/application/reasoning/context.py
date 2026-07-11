from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from application.expectation_analysis import ExpectationAnalysis
from application.operational_context import OperationalContext
from application.operational_profile import OperationalProfile
from application.planning_context import PlanningContext
from application.relationship_analysis import RelationshipAnalysis
from application.structured_assessment import StructuredAssessment
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.reasoning.assessment_summary import AssessmentSummary
from domain.reasoning.confidence_breakdown import ConfidenceBreakdown
from domain.reasoning.evidence import Evidence
from domain.reasoning.explanation import Explanation
from domain.reasoning.hypothesis import Hypothesis
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation


@dataclass(frozen=True, slots=True)
class ReasoningSignals:
    trend: DetectedTrend
    variation: DetectedVariation
    relationship_analysis: RelationshipAnalysis
    operational_context: OperationalContext
    expectation_analysis: ExpectationAnalysis
    primary_observations: tuple[Observation, ...]


@dataclass(frozen=True, slots=True)
class ReasoningArtifacts:
    signals: ReasoningSignals | None = None
    evidence: tuple[Evidence, ...] = ()
    hypotheses: tuple[Hypothesis, ...] = ()
    structured_assessment: StructuredAssessment | None = None
    assessment_summary: AssessmentSummary | None = None
    explanation: Explanation | None = None
    confidence: ConfidenceBreakdown | None = None
    planning_context: PlanningContext | None = None
    decision_context: DecisionContext | None = None
    decision_plan: DecisionPlan | None = None


@dataclass(frozen=True, slots=True)
class ReasoningMetadata:
    run_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReasoningContext:
    goal: OperationalGoal
    observations: tuple[Observation, ...]
    profile: OperationalProfile
    artifacts: ReasoningArtifacts = ReasoningArtifacts()
    metadata: ReasoningMetadata = ReasoningMetadata()

    def with_artifacts(self, **changes: object) -> ReasoningContext:
        return replace(
            self,
            artifacts=replace(self.artifacts, **changes),
        )

    def with_metadata(self, **changes: object) -> ReasoningContext:
        return replace(
            self,
            metadata=replace(self.metadata, **changes),
        )


def primary_measurement_observations(
    observations: Sequence[Observation],
) -> tuple[Observation, ...]:
    if not observations:
        return ()
    measurement_type = observations[0].measurement_type
    return tuple(
        observation
        for observation in observations
        if observation.measurement_type == measurement_type
    )

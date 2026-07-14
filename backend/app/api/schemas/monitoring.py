"""Monitoring API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from application.reasoning_trace import ReasoningTrace, TraceStep
from application.structured_assessment import StructuredAssessment
from backend.app.api.schemas.observation import ObservationResponse
from backend.app.api.schemas.telemetry import TelemetryForecastResponse
from backend.app.domain.investigation import InvestigationEvent
from backend.app.domain.notification import Notification
from backend.app.domain.operational_state import OperationalState
from backend.app.domain.reasoning import (
    AlternativeHypothesis,
    ConfidenceScore,
    Evidence,
)
from backend.app.domain.recommendation import Recommendation
from backend.app.domain.time_series import TrendAnalysis
from backend.app.domain.timeline import TimelineEvent, TimelineEventType
from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan
from domain.entities.operational_situation import OperationalSituation
from domain.reasoning.assessment_summary import AssessmentSummary
from domain.reasoning.confidence_breakdown import ConfidenceBreakdown
from domain.reasoning.evidence import Evidence as CanonicalEvidence
from domain.reasoning.explanation import Explanation
from domain.reasoning.hypothesis import Hypothesis
from domain.value_objects.location import Location


class MonitoringAssetResponse(BaseModel):
    """Known asset identifier with a lightweight fleet-summary snapshot.

    Health fields are omitted (None) when no reasoning run has completed
    for the asset yet; callers must not treat that as an error state.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "fuel-cell-stack-01",
                "name": "PEM Fuel Cell Stack 01",
                "health_status": "NORMAL",
                "health_score": 92,
                "has_active_notification": False,
            }
        }
    )

    id: str = Field(min_length=1, description="Asset identifier")
    name: str | None = Field(default=None, description="Operator-facing asset name")
    health_status: str | None = Field(
        default=None, description="Latest health status, if reasoning has run"
    )
    health_score: int | None = Field(
        default=None, description="Latest health score (0-100), if reasoning has run"
    )
    has_active_notification: bool = Field(
        default=False, description="Whether an active notification exists"
    )


class OperationalSituationResponse(BaseModel):
    id: str
    goal_id: str
    observation_ids: tuple[str, ...]
    assessment: str

    @classmethod
    def from_domain(cls, situation: OperationalSituation) -> Self:
        return cls(
            id=situation.id,
            goal_id=situation.goal_id,
            observation_ids=situation.observation_ids,
            assessment=situation.assessment,
        )


class StructuredAssessmentResponse(BaseModel):
    trend_direction: str
    variation_level: str
    has_correlations: bool
    has_contradictions: bool
    has_unexpected_expectations: bool
    has_indeterminate_expectations: bool

    @classmethod
    def from_domain(cls, assessment: StructuredAssessment) -> Self:
        return cls(
            trend_direction=assessment.trend_direction.value,
            variation_level=assessment.variation_level.value,
            has_correlations=assessment.has_correlations,
            has_contradictions=assessment.has_contradictions,
            has_unexpected_expectations=assessment.has_unexpected_expectations,
            has_indeterminate_expectations=assessment.has_indeterminate_expectations,
        )


class DecisionPlanSummaryResponse(BaseModel):
    id: str
    priority: str
    recommendation: str

    @classmethod
    def from_domain(cls, plan: DecisionPlan) -> Self:
        return cls(
            id=plan.id,
            priority=plan.priority.value,
            recommendation=plan.recommendation,
        )


class DecisionPlanResponse(BaseModel):
    id: str
    context_id: str
    created_at: datetime
    priority: str
    recommendation: str
    justification: str
    confidence: ConfidenceScoreResponse | None = None
    evidence: tuple[EvidenceResponse, ...] = ()
    alternative_hypotheses: tuple[AlternativeHypothesisResponse, ...] = ()
    expected_outcome: str | None = None

    @classmethod
    def from_domain(cls, plan: DecisionPlan) -> Self:
        return cls(
            id=plan.id,
            context_id=plan.context_id,
            created_at=plan.created_at,
            priority=plan.priority.value,
            recommendation=plan.recommendation,
            justification=plan.justification,
        )


class DecisionContextResponse(BaseModel):
    id: str
    goal_id: str
    situation_id: str
    assessment: str
    created_at: datetime

    @classmethod
    def from_domain(cls, context: DecisionContext) -> Self:
        return cls(
            id=context.id,
            goal_id=context.goal_id,
            situation_id=context.situation_id,
            assessment=context.assessment,
            created_at=context.created_at,
        )


class TraceStepResponse(BaseModel):
    name: str
    description: str

    @classmethod
    def from_domain(cls, step: TraceStep) -> Self:
        return cls(name=step.name, description=step.description)


class ReasoningTraceResponse(BaseModel):
    steps: tuple[TraceStepResponse, ...]

    @classmethod
    def from_domain(cls, trace: ReasoningTrace) -> Self:
        return cls(
            steps=tuple(TraceStepResponse.from_domain(step) for step in trace.steps)
        )


class MonitoringAssetLatestResponse(BaseModel):
    asset_id: str
    run_id: str
    timestamp: datetime
    operational_situation: OperationalSituationResponse
    structured_assessment: StructuredAssessmentResponse | None
    decision_plan: DecisionPlanSummaryResponse


class MonitoringAssetHistoryItemResponse(BaseModel):
    asset_id: str
    run_id: str
    timestamp: datetime
    operational_situation: OperationalSituationResponse
    structured_assessment: StructuredAssessmentResponse | None
    decision_plan: DecisionPlanSummaryResponse


class ConfidenceBreakdownResponse(BaseModel):
    base: int
    support: int
    consistency: int
    trend_consistency: int
    sustained_bonus: int
    penalties: int
    total: int
    rationale: str

    @classmethod
    def from_domain(cls, confidence: ConfidenceBreakdown) -> Self:
        return cls(
            base=confidence.base,
            support=confidence.support,
            consistency=confidence.consistency,
            trend_consistency=confidence.trend_consistency,
            sustained_bonus=confidence.sustained_bonus,
            penalties=confidence.penalties,
            total=confidence.total,
            rationale=confidence.rationale,
        )


class CanonicalEvidenceResponse(BaseModel):
    id: str
    description: str
    source_signal: str
    measurement_type: str
    observed_value: str
    role: str
    weight: float

    @classmethod
    def from_domain(cls, evidence: CanonicalEvidence) -> Self:
        return cls(
            id=evidence.id,
            description=evidence.description,
            source_signal=evidence.source_signal.value,
            measurement_type=evidence.measurement_type,
            observed_value=evidence.observed_value,
            role=evidence.role.value,
            weight=evidence.weight,
        )


class HypothesisResponse(BaseModel):
    id: str
    kind: str
    display_title: str
    rationale: str
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]

    @classmethod
    def from_domain(cls, hypothesis: Hypothesis) -> Self:
        return cls(
            id=hypothesis.id,
            kind=hypothesis.kind.value,
            display_title=hypothesis.display_title,
            rationale=hypothesis.rationale,
            supporting_evidence_ids=hypothesis.supporting_evidence_ids,
            contradicting_evidence_ids=hypothesis.contradicting_evidence_ids,
        )


class AssessmentSummaryResponse(BaseModel):
    trend_direction: str | None = None
    variation_level: str | None = None
    has_correlations: bool = False
    has_contradictions: bool = False
    has_unexpected_expectations: bool = False
    has_indeterminate_expectations: bool = False
    primary_hypothesis_id: str | None = None
    supporting_evidence: tuple[CanonicalEvidenceResponse, ...] = ()
    confidence_breakdown: ConfidenceBreakdownResponse | None = None

    @classmethod
    def from_domain(cls, summary: AssessmentSummary) -> Self:
        return cls(
            trend_direction=(
                summary.trend_direction.value if summary.trend_direction else None
            ),
            variation_level=(
                summary.variation_level.value if summary.variation_level else None
            ),
            has_correlations=summary.has_correlations,
            has_contradictions=summary.has_contradictions,
            has_unexpected_expectations=summary.has_unexpected_expectations,
            has_indeterminate_expectations=summary.has_indeterminate_expectations,
            primary_hypothesis_id=(
                summary.primary_hypothesis.id if summary.primary_hypothesis else None
            ),
            supporting_evidence=tuple(
                CanonicalEvidenceResponse.from_domain(item)
                for item in summary.supporting_evidence
            ),
            confidence_breakdown=(
                ConfidenceBreakdownResponse.from_domain(summary.confidence)
                if summary.confidence is not None
                else None
            ),
        )


class ExplanationResponse(BaseModel):
    summary: str
    evidence: tuple[CanonicalEvidenceResponse, ...]
    hypotheses_considered: tuple[HypothesisResponse, ...]
    caveats: tuple[str, ...]

    @classmethod
    def from_domain(cls, explanation: Explanation) -> Self:
        return cls(
            summary=explanation.summary,
            evidence=tuple(
                CanonicalEvidenceResponse.from_domain(item)
                for item in explanation.evidence
            ),
            hypotheses_considered=tuple(
                HypothesisResponse.from_domain(item)
                for item in explanation.hypotheses_considered
            ),
            caveats=explanation.caveats,
        )


class MonitoringRunDetailsResponse(BaseModel):
    run_id: str
    started_at: datetime
    observations: list[ObservationResponse]
    reasoning_trace: ReasoningTraceResponse | None
    structured_assessment: StructuredAssessmentResponse | None
    operational_situation: OperationalSituationResponse
    decision_context: DecisionContextResponse
    decision_plan: DecisionPlanResponse
    trend_analysis: TrendAnalysisResponse | None = None
    confidence_breakdown: ConfidenceBreakdownResponse | None = None
    explanation: ExplanationResponse | None = None
    hypotheses: tuple[HypothesisResponse, ...] | None = None
    assessment_summary: AssessmentSummaryResponse | None = None


class TrendAnalysisResponse(BaseModel):
    direction: str
    rate_of_change: float
    stability_score: int
    volatility_score: int
    summary: str

    @classmethod
    def from_domain(cls, analysis: TrendAnalysis) -> Self:
        return cls(
            direction=analysis.direction,
            rate_of_change=analysis.rate_of_change,
            stability_score=analysis.stability_score,
            volatility_score=analysis.volatility_score,
            summary=analysis.summary,
        )


class EvidenceResponse(BaseModel):
    id: str
    description: str
    measurement_type: str
    observed_value: str
    contribution_weight: float

    @classmethod
    def from_domain(cls, evidence: Evidence) -> Self:
        return cls(
            id=evidence.id,
            description=evidence.description,
            measurement_type=evidence.measurement_type,
            observed_value=evidence.observed_value,
            contribution_weight=evidence.contribution_weight,
        )


class ConfidenceScoreResponse(BaseModel):
    value: int
    rationale: str

    @classmethod
    def from_domain(cls, score: ConfidenceScore) -> Self:
        return cls(value=score.value, rationale=score.rationale)


class AlternativeHypothesisResponse(BaseModel):
    title: str
    reason: str
    confidence: int

    @classmethod
    def from_domain(cls, hypothesis: AlternativeHypothesis) -> Self:
        return cls(
            title=hypothesis.title,
            reason=hypothesis.reason,
            confidence=hypothesis.confidence,
        )


class TimelineEventResponse(BaseModel):
    id: str
    asset_id: str
    timestamp: datetime
    event_type: TimelineEventType
    title: str
    description: str
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, event: TimelineEvent) -> Self:
        return cls(
            id=event.id,
            asset_id=event.asset_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            title=event.title,
            description=event.description,
            metadata=event.metadata,
        )


class OperationalStateResponse(BaseModel):
    asset_id: str
    health_score: int
    health_status: str
    risk_level: str
    confidence: int
    primary_driver: str
    recommended_action: str
    last_updated: datetime

    @classmethod
    def from_domain(cls, state: OperationalState) -> Self:
        return cls(
            asset_id=state.asset_id,
            health_score=state.health_score,
            health_status=state.health_status,
            risk_level=state.risk_level,
            confidence=state.confidence,
            primary_driver=state.primary_driver,
            recommended_action=state.recommended_action,
            last_updated=state.last_updated,
        )


class RecommendationResponse(BaseModel):
    id: str
    asset_id: str
    category: str
    priority: str
    urgency: str
    title: str
    description: str
    recommended_steps: list[str]
    estimated_impact: str
    created_at: datetime

    @classmethod
    def from_domain(cls, recommendation: Recommendation) -> Self:
        return cls(
            id=recommendation.id,
            asset_id=recommendation.asset_id,
            category=recommendation.category,
            priority=recommendation.priority,
            urgency=recommendation.urgency,
            title=recommendation.title,
            description=recommendation.description,
            recommended_steps=list(recommendation.recommended_steps),
            estimated_impact=recommendation.estimated_impact,
            created_at=recommendation.created_at,
        )


class NotificationResponse(BaseModel):
    id: str
    asset_id: str
    recommendation_id: str
    severity: str
    status: str
    title: str
    message: str
    created_at: datetime

    @classmethod
    def from_domain(cls, notification: Notification) -> Self:
        return cls(
            id=notification.id,
            asset_id=notification.asset_id,
            recommendation_id=notification.recommendation_id,
            severity=notification.severity,
            status=notification.status,
            title=notification.title,
            message=notification.message,
            created_at=notification.created_at,
        )


class InvestigationTransitionRequest(BaseModel):
    """Payload for recording an operator investigation transition."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "recommendation_id": "rec-fc-stack-01-20260713T140000Z",
                "status": "ACKNOWLEDGED",
                "actor_id": "j.operator",
                "actor_display_name": "J. Operator",
                "notes": "Paged on-call, investigating cooling loop.",
            }
        }
    )

    recommendation_id: str = Field(
        min_length=1,
        description="Identifier of the recommendation this transition responds to",
    )
    status: Literal["ACKNOWLEDGED", "INVESTIGATING", "RESOLVED"] = Field(
        description="Target investigation status"
    )
    actor_id: str = Field(
        min_length=1,
        description=(
            "Stable operator identifier. Free-text today (no auth system); "
            "will become a real user id once authentication exists."
        ),
    )
    actor_display_name: str = Field(
        min_length=1,
        description="Human-readable operator name shown in the UI and timeline",
    )
    notes: str | None = Field(default=None, description="Optional operator notes")


class InvestigationTransitionResponse(BaseModel):
    """Serialized investigation transition."""

    id: str
    asset_id: str
    recommendation_id: str
    status: str
    actor_id: str
    actor_display_name: str
    occurred_at: datetime
    notes: str | None

    @classmethod
    def from_domain(cls, event: InvestigationEvent) -> Self:
        return cls(
            id=event.id,
            asset_id=event.asset_id,
            recommendation_id=event.recommendation_id,
            status=event.status,
            actor_id=event.actor_id,
            actor_display_name=event.actor_display_name,
            occurred_at=event.occurred_at,
            notes=event.notes,
        )


class LocationResponse(BaseModel):
    identifier: str

    @classmethod
    def from_domain(cls, location: Location) -> Self:
        return cls(identifier=location.identifier)


class DigitalTwinResponse(BaseModel):
    asset_id: str
    asset_name: str
    asset_type: str
    location: LocationResponse
    operational_state: OperationalStateResponse
    recommendation: RecommendationResponse
    notification: NotificationResponse | None
    investigation: InvestigationTransitionResponse | None
    latest_reasoning_run_id: str
    timeline_preview: list[TimelineEventResponse]
    telemetry_forecasts: list[TelemetryForecastResponse] = Field(
        default_factory=list,
        description=(
            "Optional ONNX-backed telemetry forecasts; does not affect reasoning"
        ),
    )
    last_updated: datetime

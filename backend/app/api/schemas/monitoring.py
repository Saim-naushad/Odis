"""Monitoring API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from application.reasoning_trace import ReasoningTrace, TraceStep
from application.structured_assessment import StructuredAssessment
from backend.app.api.schemas.observation import ObservationResponse
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


class MonitoringAssetResponse(BaseModel):
    """Known asset identifier."""

    model_config = ConfigDict(json_schema_extra={"example": {"id": "asset-stack-1"}})

    id: str = Field(min_length=1, description="Asset identifier")


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

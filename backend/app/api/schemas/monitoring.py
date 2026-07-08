"""Monitoring API response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from application.reasoning_trace import ReasoningTrace, TraceStep
from application.structured_assessment import StructuredAssessment
from backend.app.api.schemas.observation import ObservationResponse
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


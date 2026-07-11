from __future__ import annotations

from dataclasses import dataclass

from application.operational_situation_assessor import OperationalSituationAssessor
from application.reasoning.context import ReasoningContext
from domain.reasoning.assessment_summary import AssessmentSummary


@dataclass(frozen=True, slots=True)
class AssessmentStage:
    """Wrap the existing assessor without changing assessment behavior."""

    name: str = "Assessment"

    def run(self, context: ReasoningContext) -> ReasoningContext:
        signals = context.artifacts.signals
        if signals is None:
            raise ValueError("signals must be extracted before assessment")

        result = OperationalSituationAssessor().assess(
            context.goal,
            signals.primary_observations,
            signals.trend,
            signals.variation,
            relationship_analysis=signals.relationship_analysis,
            expectation_analysis=signals.expectation_analysis,
        )
        summary = AssessmentSummary(
            situation=result.situation,
            trend_direction=result.structured.trend_direction,
            variation_level=result.structured.variation_level,
            has_correlations=result.structured.has_correlations,
            has_contradictions=result.structured.has_contradictions,
            has_unexpected_expectations=(
                result.structured.has_unexpected_expectations
            ),
            has_indeterminate_expectations=(
                result.structured.has_indeterminate_expectations
            ),
            primary_hypothesis=(
                context.artifacts.hypotheses[0]
                if context.artifacts.hypotheses
                else None
            ),
            supporting_evidence=context.artifacts.evidence,
        )
        return context.with_artifacts(
            structured_assessment=result.structured,
            assessment_summary=summary,
        )

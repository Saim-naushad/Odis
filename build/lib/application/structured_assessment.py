from __future__ import annotations

from dataclasses import dataclass

from application.expectation_analysis import ExpectationAnalysis
from application.relationship_analysis import RelationshipAnalysis
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel


@dataclass(frozen=True)
class StructuredAssessment:
    trend_direction: TrendDirection
    variation_level: VariationLevel
    has_correlations: bool
    has_contradictions: bool
    has_unexpected_expectations: bool
    has_indeterminate_expectations: bool

    @classmethod
    def from_reasoning(
        cls,
        trend: DetectedTrend,
        variation: DetectedVariation,
        relationship_analysis: RelationshipAnalysis | None = None,
        expectation_analysis: ExpectationAnalysis | None = None,
    ) -> StructuredAssessment:
        analysis = expectation_analysis or ExpectationAnalysis(evaluations=())
        return cls(
            trend_direction=trend.direction,
            variation_level=variation.level,
            has_correlations=bool(
                relationship_analysis and relationship_analysis.correlations
            ),
            has_contradictions=bool(
                relationship_analysis and relationship_analysis.contradictions
            ),
            has_unexpected_expectations=analysis.has_unexpected,
            has_indeterminate_expectations=analysis.has_indeterminate,
        )

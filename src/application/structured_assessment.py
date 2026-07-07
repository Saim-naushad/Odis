from __future__ import annotations

from dataclasses import dataclass

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

    @classmethod
    def from_reasoning(
        cls,
        trend: DetectedTrend,
        variation: DetectedVariation,
        relationship_analysis: RelationshipAnalysis | None = None,
    ) -> StructuredAssessment:
        return cls(
            trend_direction=trend.direction,
            variation_level=variation.level,
            has_correlations=bool(
                relationship_analysis and relationship_analysis.correlations
            ),
            has_contradictions=bool(
                relationship_analysis and relationship_analysis.contradictions
            ),
        )

"""Mapping between application structured assessments and ORM models."""

from application.structured_assessment import StructuredAssessment
from backend.app.infrastructure.database.models.structured_assessment import (
    StructuredAssessmentModel,
)
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel


def structured_assessment_to_model(
    run_id: str,
    assessment: StructuredAssessment,
) -> StructuredAssessmentModel:
    """Map an application structured assessment to its SQLAlchemy representation."""
    return StructuredAssessmentModel(
        run_id=run_id,
        trend_direction=assessment.trend_direction.value,
        variation_level=assessment.variation_level.value,
        has_correlations=assessment.has_correlations,
        has_contradictions=assessment.has_contradictions,
        has_unexpected_expectations=assessment.has_unexpected_expectations,
        has_indeterminate_expectations=assessment.has_indeterminate_expectations,
    )


def structured_assessment_to_domain(
    model: StructuredAssessmentModel,
) -> StructuredAssessment:
    """Map a SQLAlchemy structured assessment row to the application model."""
    return StructuredAssessment(
        trend_direction=TrendDirection(model.trend_direction),
        variation_level=VariationLevel(model.variation_level),
        has_correlations=model.has_correlations,
        has_contradictions=model.has_contradictions,
        has_unexpected_expectations=model.has_unexpected_expectations,
        has_indeterminate_expectations=model.has_indeterminate_expectations,
    )

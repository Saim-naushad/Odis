from application.expectation import Expectation
from application.expectation_analysis import ExpectationAnalysis
from application.expectation_evaluator import (
    ExpectationEvaluation,
    ExpectationEvaluator,
)
from application.structured_assessment import StructuredAssessment
from domain.value_objects.detected_trend import DetectedTrend
from domain.value_objects.detected_variation import DetectedVariation
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel
from tests.builders import build_measurement_type


def _trend() -> DetectedTrend:
    measurement_type = build_measurement_type()
    return DetectedTrend(
        asset_id="asset-1",
        measurement_type=measurement_type,
        direction=TrendDirection.INCREASING,
    )


def _variation() -> DetectedVariation:
    measurement_type = build_measurement_type()
    return DetectedVariation(
        asset_id="asset-1",
        measurement_type=measurement_type,
        level=VariationLevel.LOW,
    )


def _evaluation(*, satisfied: bool | None) -> ExpectationEvaluation:
    return ExpectationEvaluator().evaluate(
        Expectation(
            name="Cooling tracks load",
            description="Coolant flow should increase with electrical load.",
        ),
        satisfied,
    )


def test_from_reasoning_without_expectation_analysis_uses_empty_flags() -> None:
    assessment = StructuredAssessment.from_reasoning(_trend(), _variation())

    assert assessment.has_unexpected_expectations is False
    assert assessment.has_indeterminate_expectations is False


def test_from_reasoning_populates_expectation_flags_from_analysis() -> None:
    analysis = ExpectationAnalysis(
        evaluations=(
            _evaluation(satisfied=True),
            _evaluation(satisfied=False),
            _evaluation(satisfied=None),
        )
    )

    assessment = StructuredAssessment.from_reasoning(
        _trend(),
        _variation(),
        expectation_analysis=analysis,
    )

    assert assessment.has_unexpected_expectations is True
    assert assessment.has_indeterminate_expectations is True


def test_from_reasoning_preserves_existing_assessment_fields() -> None:
    assessment = StructuredAssessment.from_reasoning(_trend(), _variation())

    assert assessment.trend_direction == TrendDirection.INCREASING
    assert assessment.variation_level == VariationLevel.LOW
    assert assessment.has_correlations is False
    assert assessment.has_contradictions is False

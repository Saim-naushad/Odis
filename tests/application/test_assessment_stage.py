import pytest

from application.operational_profile import OperationalProfile
from application.reasoning.assessment_stage import AssessmentStage
from application.reasoning.context import ReasoningContext
from application.reasoning.evidence_generation_stage import EvidenceGenerationStage
from application.reasoning.hypothesis_stage import HypothesisStage
from application.reasoning.signal_extraction_stage import SignalExtractionStage
from domain.value_objects import TrendDirection, VariationLevel
from tests.builders import build_goal, build_observation_sequence


def _pre_assessment_context(values: list[float]) -> ReasoningContext:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence(values),
        profile=OperationalProfile.default(),
    )
    for stage in (
        SignalExtractionStage(),
        EvidenceGenerationStage(),
        HypothesisStage(),
    ):
        context = stage.run(context)
    return context


def test_assessment_stage_requires_signals() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([10.0, 20.0]),
        profile=OperationalProfile.default(),
    )

    with pytest.raises(ValueError, match="signals must be extracted"):
        AssessmentStage().run(context)


def test_assessment_stage_preserves_existing_assessment_behavior() -> None:
    # At least _MIN_SAMPLES_FOR_DIRECTIONAL_TREND observations are required
    # for TrendDetector to classify this as "increasing" rather than STABLE.
    context = AssessmentStage().run(
        _pre_assessment_context([32.0, 36.5, 41.0, 45.5, 50.0, 54.5, 59.0, 63.5])
    )
    summary = context.artifacts.assessment_summary
    structured = context.artifacts.structured_assessment

    assert summary is not None
    assert summary.situation is not None
    assert summary.situation.assessment == "Increasing operational stress detected"
    assert structured is not None
    assert structured.trend_direction == TrendDirection.INCREASING
    assert structured.variation_level == VariationLevel.LOW
    assert summary.trend_direction == structured.trend_direction
    assert summary.variation_level == structured.variation_level
    assert summary.supporting_evidence == context.artifacts.evidence
    assert summary.confidence is None
    assert context.artifacts.explanation is None

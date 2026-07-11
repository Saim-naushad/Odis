import pytest

from application.operational_profile import OperationalProfile
from application.reasoning.assessment_stage import AssessmentStage
from application.reasoning.confidence_scorer import score_assessment_confidence
from application.reasoning.confidence_stage import ConfidenceStage
from application.reasoning.context import ReasoningContext
from application.reasoning.evidence_generation_stage import EvidenceGenerationStage
from application.reasoning.hypothesis_stage import HypothesisStage
from application.reasoning.signal_extraction_stage import SignalExtractionStage
from tests.builders import build_goal, build_observation_sequence


def _assessed_context(values: list[float]) -> ReasoningContext:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence(values),
        profile=OperationalProfile.default(),
    )
    for stage in (
        SignalExtractionStage(),
        EvidenceGenerationStage(),
        HypothesisStage(),
        AssessmentStage(),
    ):
        context = stage.run(context)
    return context


def test_confidence_stage_requires_assessment() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([10.0, 20.0]),
        profile=OperationalProfile.default(),
    )

    with pytest.raises(ValueError, match="assessment must be completed"):
        ConfidenceStage().run(context)


def test_confidence_stage_scores_assessment_confidence_deterministically() -> None:
    context = ConfidenceStage().run(_assessed_context([32.0, 36.5, 41.0, 45.5, 50.0]))
    confidence = context.artifacts.confidence
    summary = context.artifacts.assessment_summary

    assert confidence is not None
    assert summary is not None
    assert summary.confidence == confidence
    assert 0 <= confidence.total <= 100
    assert confidence.base == 35
    assert confidence.support == 24
    assert confidence.rationale.startswith("Base 35.")
    assert "Assessment:" in confidence.rationale


def test_confidence_increases_with_more_supporting_observations() -> None:
    low = score_assessment_confidence(
        assessment_summary=_assessed_context([10.0, 20.0]).artifacts.assessment_summary,  # type: ignore[arg-type]
        evidence=(),
        hypotheses=(),
        structured_assessment=_assessed_context([10.0, 20.0]).artifacts.structured_assessment,  # type: ignore[arg-type]
        primary_observations=_assessed_context([10.0, 20.0]).artifacts.signals.primary_observations,  # type: ignore[union-attr]
    )
    high = score_assessment_confidence(
        assessment_summary=_assessed_context([10.0, 20.0, 30.0]).artifacts.assessment_summary,  # type: ignore[arg-type]
        evidence=(),
        hypotheses=(),
        structured_assessment=_assessed_context([10.0, 20.0, 30.0]).artifacts.structured_assessment,  # type: ignore[arg-type]
        primary_observations=_assessed_context([10.0, 20.0, 30.0]).artifacts.signals.primary_observations,  # type: ignore[union-attr]
    )

    assert high.total >= low.total
    assert high.support > low.support

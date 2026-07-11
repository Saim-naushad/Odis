import pytest

from application.operational_profile import OperationalProfile
from application.reasoning.assessment_stage import AssessmentStage
from application.reasoning.confidence_stage import ConfidenceStage
from application.reasoning.context import ReasoningContext
from application.reasoning.evidence_generation_stage import EvidenceGenerationStage
from application.reasoning.explanation_builder import build_explanation
from application.reasoning.explanation_stage import ExplanationStage
from application.reasoning.hypothesis_stage import HypothesisStage
from application.reasoning.signal_extraction_stage import SignalExtractionStage
from tests.builders import build_goal, build_observation_sequence


def _confidence_context(values: list[float]) -> ReasoningContext:
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
        ConfidenceStage(),
    ):
        context = stage.run(context)
    return context


def test_explanation_builder_requires_situation() -> None:
    context = _confidence_context([32.0, 36.5, 41.0, 45.5, 50.0])
    summary = context.artifacts.assessment_summary
    confidence = context.artifacts.confidence
    assert summary is not None
    assert confidence is not None

    explanation = build_explanation(
        assessment_summary=summary,
        evidence=context.artifacts.evidence,
        hypotheses=context.artifacts.hypotheses,
        confidence=confidence,
    )

    assert explanation.summary.startswith("Assessment:")
    assert explanation.evidence == context.artifacts.evidence
    assert explanation.hypotheses_considered == context.artifacts.hypotheses


def test_explanation_stage_requires_confidence() -> None:
    context = ReasoningContext(
        goal=build_goal(),
        observations=build_observation_sequence([10.0, 20.0]),
        profile=OperationalProfile.default(),
    )

    with pytest.raises(ValueError, match="assessment and confidence must exist"):
        ExplanationStage().run(context)


def test_explanation_stage_populates_structured_explanation() -> None:
    context = ExplanationStage().run(
        _confidence_context([32.0, 36.5, 41.0, 45.5, 50.0])
    )
    explanation = context.artifacts.explanation

    assert explanation is not None
    assert explanation.evidence
    assert explanation.hypotheses_considered
    assert isinstance(explanation.caveats, tuple)

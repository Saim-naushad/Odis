import pytest

from domain.reasoning.assessment_summary import AssessmentSummary
from domain.reasoning.confidence_breakdown import ConfidenceBreakdown
from domain.reasoning.evidence import Evidence, EvidenceRole, EvidenceSourceSignal
from domain.reasoning.explanation import Explanation
from domain.reasoning.hypothesis import Hypothesis, HypothesisKind


def test_evidence_validates_weight_bounds() -> None:
    with pytest.raises(ValueError, match="weight must be between 0 and 1"):
        Evidence(
            id="bad",
            description="Invalid weight",
            source_signal=EvidenceSourceSignal.LATEST_READING,
            measurement_type="temperature",
            observed_value="1.0 celsius",
            role=EvidenceRole.PRIMARY_SUPPORT,
            weight=1.5,
        )


def test_hypothesis_exposes_display_title_from_kind() -> None:
    hypothesis = Hypothesis(
        id="hypothesis-load-change",
        kind=HypothesisKind.LOAD_CHANGE,
        rationale="Transient load shift.",
        supporting_evidence_ids=("latest_reading",),
    )

    assert hypothesis.display_title == "Load change"


def test_assessment_summary_is_factual_and_excludes_explanation() -> None:
    summary = AssessmentSummary()

    assert summary.situation is None
    assert summary.primary_hypothesis is None
    assert summary.supporting_evidence == ()
    assert summary.confidence is None
    assert not hasattr(summary, "explanation")


def test_explanation_references_structured_evidence_objects() -> None:
    evidence = (
        Evidence(
            id=EvidenceSourceSignal.LATEST_READING,
            description="Latest reading",
            source_signal=EvidenceSourceSignal.LATEST_READING,
            measurement_type="temperature",
            observed_value="12.0 celsius",
            role=EvidenceRole.PRIMARY_SUPPORT,
            weight=0.35,
        ),
    )
    hypothesis = Hypothesis(
        id="hypothesis-unknown",
        kind=HypothesisKind.UNKNOWN,
        rationale="Insufficient history.",
        supporting_evidence_ids=(evidence[0].id,),
    )

    explanation = Explanation(
        summary="Assessment supported by recent readings.",
        evidence=evidence,
        hypotheses_considered=(hypothesis,),
        caveats=("Limited observation history.",),
    )

    assert explanation.evidence[0].id == EvidenceSourceSignal.LATEST_READING


def test_confidence_breakdown_validates_total_range() -> None:
    with pytest.raises(ValueError, match="total must be between 0 and 100"):
        ConfidenceBreakdown(
            base=35,
            support=10,
            consistency=5,
            trend_consistency=0,
            sustained_bonus=0,
            penalties=0,
            total=150,
            rationale="invalid",
        )

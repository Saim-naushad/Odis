from __future__ import annotations

from domain.reasoning.assessment_summary import AssessmentSummary
from domain.reasoning.confidence_breakdown import ConfidenceBreakdown
from domain.reasoning.evidence import Evidence
from domain.reasoning.explanation import Explanation
from domain.reasoning.hypothesis import Hypothesis


def build_explanation(
    *,
    assessment_summary: AssessmentSummary,
    evidence: tuple[Evidence, ...],
    hypotheses: tuple[Hypothesis, ...],
    confidence: ConfidenceBreakdown,
) -> Explanation:
    """Build a deterministic explanation from structured reasoning artifacts."""
    if assessment_summary.situation is None:
        raise ValueError("assessment summary must include a situation")

    assessment_text = assessment_summary.situation.assessment
    summary = (
        f"Assessment: {assessment_text} "
        f"Confidence in assessment: {confidence.total}/100."
    )

    caveats: list[str] = []
    if assessment_summary.has_contradictions:
        caveats.append("Cross-measurement contradictions weaken certainty.")
    if assessment_summary.has_unexpected_expectations:
        caveats.append("Unexpected expectation signals were detected.")
    if assessment_summary.has_indeterminate_expectations:
        caveats.append("Some expectations remain indeterminate.")
    if not evidence:
        caveats.append("Limited supporting evidence is available.")
    if not hypotheses:
        caveats.append("No alternative hypotheses were generated.")

    return Explanation(
        summary=summary,
        evidence=evidence,
        hypotheses_considered=hypotheses,
        caveats=tuple(caveats),
    )

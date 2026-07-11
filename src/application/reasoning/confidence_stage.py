from __future__ import annotations

from dataclasses import dataclass

from application.reasoning.confidence_scorer import (
    apply_confidence_to_summary,
    score_assessment_confidence,
)
from application.reasoning.context import ReasoningContext


@dataclass(frozen=True, slots=True)
class ConfidenceStage:
    """Score confidence in the produced assessment."""

    name: str = "Confidence"

    def run(self, context: ReasoningContext) -> ReasoningContext:
        summary = context.artifacts.assessment_summary
        structured = context.artifacts.structured_assessment
        signals = context.artifacts.signals
        if summary is None or structured is None or signals is None:
            raise ValueError("assessment must be completed before confidence scoring")

        confidence = score_assessment_confidence(
            assessment_summary=summary,
            evidence=context.artifacts.evidence,
            hypotheses=context.artifacts.hypotheses,
            structured_assessment=structured,
            primary_observations=signals.primary_observations,
        )
        return context.with_artifacts(
            confidence=confidence,
            assessment_summary=apply_confidence_to_summary(
                assessment_summary=summary,
                confidence=confidence,
            ),
        )

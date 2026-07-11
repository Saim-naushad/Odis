from __future__ import annotations

from dataclasses import dataclass

from application.reasoning.context import ReasoningContext
from application.reasoning.explanation_builder import build_explanation


@dataclass(frozen=True, slots=True)
class ExplanationStage:
    """Generate a deterministic explanation from reasoning artifacts."""

    name: str = "Explanation"

    def run(self, context: ReasoningContext) -> ReasoningContext:
        summary = context.artifacts.assessment_summary
        confidence = context.artifacts.confidence
        if summary is None or confidence is None:
            raise ValueError(
                "assessment and confidence must exist before explanation generation"
            )

        explanation = build_explanation(
            assessment_summary=summary,
            evidence=context.artifacts.evidence,
            hypotheses=context.artifacts.hypotheses,
            confidence=confidence,
        )
        return context.with_artifacts(explanation=explanation)

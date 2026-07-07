from __future__ import annotations

from dataclasses import dataclass

from application.structured_assessment import StructuredAssessment


@dataclass(frozen=True)
class PlanningContext:
    has_relationships: bool
    has_contradictions: bool

    @classmethod
    def from_assessment(cls, assessment: StructuredAssessment) -> PlanningContext:
        return cls(
            has_relationships=bool(
                assessment.has_correlations or assessment.has_contradictions
            ),
            has_contradictions=bool(assessment.has_contradictions),
        )

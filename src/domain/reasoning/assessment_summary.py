from __future__ import annotations

from dataclasses import dataclass

from domain.entities.operational_situation import OperationalSituation
from domain.reasoning.confidence_breakdown import ConfidenceBreakdown
from domain.reasoning.evidence import Evidence
from domain.reasoning.hypothesis import Hypothesis


@dataclass(frozen=True, slots=True)
class AssessmentSummary:
    """Factual reasoning outputs produced by assessment.

    Does not embed Explanation; presentation is generated separately.
    """

    situation: OperationalSituation | None = None
    primary_hypothesis: Hypothesis | None = None
    supporting_evidence: tuple[Evidence, ...] = ()
    confidence: ConfidenceBreakdown | None = None

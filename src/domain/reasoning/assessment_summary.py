from __future__ import annotations

from dataclasses import dataclass

from domain.entities.operational_situation import OperationalSituation
from domain.reasoning.confidence_breakdown import ConfidenceBreakdown
from domain.reasoning.evidence import Evidence
from domain.reasoning.hypothesis import Hypothesis
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel


@dataclass(frozen=True, slots=True)
class AssessmentSummary:
    """Factual reasoning outputs produced by assessment.

    Does not embed Explanation; presentation is generated separately.
    """

    situation: OperationalSituation | None = None
    trend_direction: TrendDirection | None = None
    variation_level: VariationLevel | None = None
    has_correlations: bool = False
    has_contradictions: bool = False
    has_unexpected_expectations: bool = False
    has_indeterminate_expectations: bool = False
    primary_hypothesis: Hypothesis | None = None
    supporting_evidence: tuple[Evidence, ...] = ()
    confidence: ConfidenceBreakdown | None = None

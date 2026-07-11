from __future__ import annotations

from dataclasses import replace

from application.structured_assessment import StructuredAssessment
from domain.entities.observation import Observation
from domain.reasoning.assessment_summary import AssessmentSummary
from domain.reasoning.confidence_breakdown import ConfidenceBreakdown
from domain.reasoning.evidence import Evidence
from domain.reasoning.hypothesis import Hypothesis
from domain.value_objects.trend_direction import TrendDirection
from domain.value_objects.variation_level import VariationLevel


def _is_monotonic_recent(primary_observations: tuple[Observation, ...]) -> bool:
    if len(primary_observations) < 3:
        return False
    first, second, third = primary_observations[-3:]
    increasing = first.value <= second.value <= third.value
    decreasing = first.value >= second.value >= third.value
    return increasing or decreasing


def score_assessment_confidence(
    *,
    assessment_summary: AssessmentSummary,
    evidence: tuple[Evidence, ...],
    hypotheses: tuple[Hypothesis, ...],
    structured_assessment: StructuredAssessment,
    primary_observations: tuple[Observation, ...],
) -> ConfidenceBreakdown:
    """Score confidence in the produced assessment using deterministic signals."""
    _ = evidence
    _ = hypotheses

    contradictions = structured_assessment.has_contradictions
    variation_high = structured_assessment.variation_level == VariationLevel.HIGH
    trend_direction = structured_assessment.trend_direction

    base = 35
    n_supporting = len(primary_observations)
    support = min(25, 8 * min(n_supporting, 3))

    stable = not variation_high and not contradictions
    consistency = 15 if stable else 5

    trend_consistency = 0
    if trend_direction in {TrendDirection.INCREASING, TrendDirection.DECREASING}:
        trend_consistency = 12 if not variation_high else 4
    elif trend_direction == TrendDirection.STABLE:
        trend_consistency = 8

    sustained = (
        _is_monotonic_recent(primary_observations)
        and trend_direction != TrendDirection.STABLE
    )
    sustained_bonus = 6 if sustained else 0

    penalties = 0
    if contradictions:
        penalties -= 12
    if structured_assessment.has_unexpected_expectations:
        penalties -= 6

    raw = (
        base
        + support
        + consistency
        + trend_consistency
        + sustained_bonus
        + penalties
    )
    total = max(0, min(100, int(raw)))

    penalty_clause = (
        "Penalty -12 for contradictions."
        if contradictions
        else "No contradiction penalty."
    )
    unexpected_clause = (
        "Penalty -6 for unexpected expectations."
        if structured_assessment.has_unexpected_expectations
        else "No unexpected-expectation penalty."
    )
    sustained_clause = (
        "Sustained directional change observed."
        if sustained
        else "No sustained directional change."
    )
    assessment_text = (
        assessment_summary.situation.assessment
        if assessment_summary.situation is not None
        else "unknown assessment"
    )
    rationale = (
        f"Base {base}. Support {support} from {n_supporting} observations. "
        f"Consistency {consistency} ({'stable' if stable else 'mixed'}). "
        f"Trend {trend_consistency} (direction {trend_direction.value}). "
        f"{sustained_clause} "
        f"{penalty_clause} "
        f"{unexpected_clause} "
        f"Assessment: {assessment_text}"
    )
    return ConfidenceBreakdown(
        base=base,
        support=support,
        consistency=consistency,
        trend_consistency=trend_consistency,
        sustained_bonus=sustained_bonus,
        penalties=penalties,
        total=total,
        rationale=rationale,
    )


def apply_confidence_to_summary(
    *,
    assessment_summary: AssessmentSummary,
    confidence: ConfidenceBreakdown,
) -> AssessmentSummary:
    return replace(assessment_summary, confidence=confidence)

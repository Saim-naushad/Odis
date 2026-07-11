"""Compatibility adapters between canonical src reasoning and platform APIs."""

from __future__ import annotations

from dataclasses import dataclass

from application.operational_profile import OperationalProfile
from application.reasoning.assessment_stage import AssessmentStage
from application.reasoning.confidence_stage import ConfidenceStage
from application.reasoning.context import ReasoningContext
from application.reasoning.evidence_generation_stage import EvidenceGenerationStage
from application.reasoning.explanation_stage import ExplanationStage
from application.reasoning.hypothesis_stage import HypothesisStage
from application.reasoning.signal_extraction_stage import SignalExtractionStage
from application.reasoning.stage import ReasoningStage
from backend.app.application.time_series_analysis import (
    TrendDiagnostics,
    analyze_trend,
    analyze_trend_diagnostics,
)
from backend.app.domain.reasoning import (
    AlternativeHypothesis,
    ConfidenceScore,
)
from backend.app.domain.reasoning import (
    Evidence as BackendEvidence,
)
from backend.app.domain.time_series import TrendAnalysis
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.reasoning.assessment_summary import AssessmentSummary
from domain.reasoning.confidence_breakdown import ConfidenceBreakdown
from domain.reasoning.evidence import Evidence as CanonicalEvidence
from domain.reasoning.explanation import Explanation
from domain.reasoning.hypothesis import Hypothesis

REASONING_ENRICHMENT_STAGES: tuple[ReasoningStage, ...] = (
    SignalExtractionStage(),
    EvidenceGenerationStage(),
    HypothesisStage(),
    AssessmentStage(),
    ConfidenceStage(),
    ExplanationStage(),
)


def build_reasoning_context_through_explanation(
    *,
    goal: OperationalGoal,
    observations: tuple[Observation, ...] | list[Observation],
    profile: OperationalProfile | None = None,
) -> ReasoningContext:
    """Run canonical reasoning stages up to explanation (excluding planning)."""
    context = ReasoningContext(
        goal=goal,
        observations=tuple(observations),
        profile=profile or OperationalProfile.default(),
    )
    for stage in REASONING_ENRICHMENT_STAGES:
        context = stage.run(context)
    return context


def to_backend_evidence(evidence: CanonicalEvidence) -> BackendEvidence:
    return BackendEvidence(
        id=evidence.id,
        description=evidence.description,
        measurement_type=evidence.measurement_type,
        observed_value=evidence.observed_value,
        contribution_weight=evidence.weight,
    )


def to_confidence_score(confidence: ConfidenceBreakdown) -> ConfidenceScore:
    return ConfidenceScore(value=confidence.total, rationale=confidence.rationale)


def hypothesis_to_alternative(
    hypothesis: Hypothesis,
    *,
    assessment_confidence: int,
) -> AlternativeHypothesis:
    alternative_confidence = max(
        5,
        min(60, int(assessment_confidence * 0.35)),
    )
    return AlternativeHypothesis(
        title=hypothesis.display_title,
        reason=hypothesis.rationale,
        confidence=alternative_confidence,
    )


def alternatives_from_hypotheses(
    hypotheses: tuple[Hypothesis, ...],
    *,
    assessment_confidence: int,
) -> tuple[AlternativeHypothesis, ...]:
    if not hypotheses:
        return ()
    return tuple(
        hypothesis_to_alternative(
            hypothesis,
            assessment_confidence=assessment_confidence,
        )
        for hypothesis in hypotheses[:2]
    )


def canonical_evidence_from_context(
    context: ReasoningContext,
) -> tuple[BackendEvidence, ...]:
    return tuple(to_backend_evidence(item) for item in context.artifacts.evidence)


def assessment_summary_from_context(
    context: ReasoningContext,
) -> AssessmentSummary | None:
    return context.artifacts.assessment_summary


def explanation_from_context(context: ReasoningContext) -> Explanation | None:
    return context.artifacts.explanation


# Legacy explainable decision adapter (monitoring state + run details)


@dataclass(frozen=True, slots=True)
class ExplainableDecision:
    assessment: str
    trend_analysis: TrendAnalysis
    evidence: tuple[BackendEvidence, ...]
    confidence: ConfidenceScore
    alternative_hypotheses: tuple[AlternativeHypothesis, ...]
    recommendation: str
    expected_outcome: str


def build_explainable_decision(
    *,
    assessment: str,
    observations: list[Observation],
    decision_plan: DecisionPlan,
    structured_assessment: object | None,
) -> ExplainableDecision:
    primary_observations = _primary_measurement_observations(observations)
    measurement_type = (
        str(
            getattr(
                primary_observations[0].measurement_type,
                "name",
                primary_observations[0].measurement_type,
            )
        )
        if primary_observations
        else None
    )
    trend_analysis = analyze_trend(
        primary_observations,
        observation_window=5,
        measurement_label=measurement_type,
    )
    diagnostics = analyze_trend_diagnostics(primary_observations, observation_window=5)
    evidence = _build_legacy_evidence(
        trend_analysis=trend_analysis,
        primary_observations=primary_observations,
        decision_plan=decision_plan,
    )
    confidence = _calculate_legacy_confidence(
        assessment=assessment,
        trend_analysis=trend_analysis,
        trend_diagnostics=diagnostics,
        primary_observations=primary_observations,
        structured_assessment=structured_assessment,
        decision_plan=decision_plan,
    )
    alternatives = _build_legacy_alternatives(
        assessment=assessment,
        primary_observations=primary_observations,
        structured_assessment=structured_assessment,
        primary_confidence=confidence.value,
    )
    expected_outcome = _expected_outcome(
        assessment=assessment,
        recommendation=decision_plan.recommendation,
        priority=decision_plan.priority.value,
    )
    return ExplainableDecision(
        assessment=assessment,
        trend_analysis=trend_analysis,
        evidence=evidence,
        confidence=confidence,
        alternative_hypotheses=alternatives,
        recommendation=decision_plan.recommendation,
        expected_outcome=expected_outcome,
    )


def _primary_measurement_observations(
    observations: list[Observation],
) -> list[Observation]:
    if not observations:
        return []
    measurement_type = observations[0].measurement_type
    primary = [obs for obs in observations if obs.measurement_type == measurement_type]
    primary.sort(key=lambda obs: (obs.timestamp, obs.id))
    return primary


def _format_observed_value(observation: Observation) -> str:
    return f"{observation.value} {observation.unit}".strip()


def _build_legacy_evidence(
    *,
    trend_analysis: TrendAnalysis,
    primary_observations: list[Observation],
    decision_plan: DecisionPlan,
) -> tuple[BackendEvidence, ...]:
    evidences: list[BackendEvidence] = []
    raw_measurement_type = (
        primary_observations[0].measurement_type if primary_observations else "unknown"
    )
    measurement_type = str(getattr(raw_measurement_type, "name", raw_measurement_type))

    if primary_observations:
        latest = primary_observations[-1]
        evidences.append(
            BackendEvidence(
                id="latest_reading",
                description="Latest recorded reading is considered in the decision.",
                measurement_type=measurement_type,
                observed_value=_format_observed_value(latest),
                contribution_weight=0.35,
            )
        )

    evidences.append(
        BackendEvidence(
            id="trend_analysis",
            description="Recent time-series behavior contributes to the decision.",
            measurement_type=(
                str(
                    getattr(
                        primary_observations[0].measurement_type,
                        "name",
                        primary_observations[0].measurement_type,
                    )
                )
                if primary_observations
                else "unknown"
            ),
            observed_value=trend_analysis.summary,
            contribution_weight=0.25,
        )
    )

    if len(primary_observations) >= 2:
        prev = primary_observations[-2]
        latest = primary_observations[-1]
        delta = latest.value - prev.value
        evidences.append(
            BackendEvidence(
                id="recent_delta",
                description=(
                    "Change between the two most recent readings supports the "
                    "assessment."
                ),
                measurement_type=measurement_type,
                observed_value=f"Δ {delta:.2f} {latest.unit} (latest - previous)",
                contribution_weight=0.3,
            )
        )

    if primary_observations:
        count = len(primary_observations)
        evidences.append(
            BackendEvidence(
                id="sample_support",
                description=(
                    "Multiple observations reduce the chance of a one-off anomaly."
                ),
                measurement_type=measurement_type,
                observed_value=f"{count} supporting observations",
                contribution_weight=0.2 if count >= 3 else 0.15,
            )
        )

    evidences.append(
        BackendEvidence(
            id="planner_alignment",
            description=(
                "Recommendation is consistent with the operational assessment rules."
            ),
            measurement_type=measurement_type,
            observed_value=(
                f"{decision_plan.priority.value} priority -> "
                f"{decision_plan.recommendation}"
            ),
            contribution_weight=0.15,
        )
    )

    return tuple(evidences)


def _calculate_legacy_confidence(
    *,
    assessment: str,
    trend_analysis: TrendAnalysis,
    trend_diagnostics: TrendDiagnostics | None,
    primary_observations: list[Observation],
    structured_assessment: object | None,
    decision_plan: DecisionPlan,
) -> ConfidenceScore:
    contradictions = False
    variation_high = False

    if structured_assessment is not None:
        contradictions = bool(
            getattr(structured_assessment, "has_contradictions", False)
        )
        variation_level = getattr(structured_assessment, "variation_level", None)
        variation_level_value = getattr(
            variation_level, "value", str(variation_level or "")
        ).casefold()
        variation_high = "high" in variation_level_value

    n_supporting = len(primary_observations)
    support = min(25, 8 * min(n_supporting, 3))

    severity_map = {"high": 25, "medium": 15, "low": 5}
    severity = severity_map.get(decision_plan.priority.value.casefold(), 10)

    sustained = False
    if trend_diagnostics is not None and trend_analysis.direction != "stable":
        sustained = (
            trend_diagnostics.monotonicity >= 0.85
            and trend_analysis.stability_score >= 70
        )

    trend_consistency = 0
    if trend_analysis.stability_score >= 75:
        trend_consistency = 12
    elif trend_analysis.stability_score >= 60:
        trend_consistency = 8
    elif trend_analysis.stability_score >= 45:
        trend_consistency = 4

    sustained_bonus = 6 if sustained else 0

    stable = trend_analysis.stability_score >= 65 and not variation_high
    consistency = 15 if stable else 5

    penalties = -12 if contradictions else 0

    base = 35
    raw = (
        base
        + support
        + severity
        + consistency
        + trend_consistency
        + sustained_bonus
        + penalties
    )
    value = max(0, min(100, int(raw)))

    penalty_clause = (
        "Penalty -12 for contradictions."
        if contradictions
        else "No contradiction penalty."
    )
    sustained_clause = (
        "Sustained directional change observed."
        if sustained
        else "No sustained directional change."
    )
    rationale = (
        f"Base {base}. Support {support} from {n_supporting} observations. "
        f"Severity {severity} from {decision_plan.priority.value} priority. "
        f"Consistency {consistency} ({'stable' if stable else 'mixed'}). "
        f"Trend {trend_consistency} (stability {trend_analysis.stability_score}/100, "
        f"direction {trend_analysis.direction}). "
        f"{sustained_clause} "
        f"{penalty_clause} "
        f"Assessment: {assessment}"
    )
    return ConfidenceScore(value=value, rationale=rationale)


def _build_legacy_alternatives(
    *,
    assessment: str,
    primary_observations: list[Observation],
    structured_assessment: object | None,
    primary_confidence: int,
) -> tuple[AlternativeHypothesis, ...]:
    raw_measurement_type = (
        primary_observations[0].measurement_type if primary_observations else "signal"
    )
    measurement_type = str(getattr(raw_measurement_type, "name", raw_measurement_type))
    normalized = assessment.casefold()

    contradictions = (
        bool(getattr(structured_assessment, "has_contradictions", False))
        if structured_assessment
        else False
    )
    variation_level = (
        getattr(getattr(structured_assessment, "variation_level", None), "value", "")
        if structured_assessment
        else ""
    )
    variation_high = "high" in str(variation_level).casefold()

    alternatives: list[AlternativeHypothesis] = []

    if variation_high or contradictions:
        confidence = max(5, min(60, int(primary_confidence * 0.35)))
        alternatives.append(
            AlternativeHypothesis(
                title="Sensor drift",
                reason=(
                    "High variability or contradictory signals can indicate "
                    "measurement drift "
                    f"rather than a true change in {measurement_type}."
                ),
                confidence=confidence,
            )
        )
    else:
        confidence = max(5, min(40, int(primary_confidence * 0.22)))
        alternatives.append(
            AlternativeHypothesis(
                title="Temporary overload",
                reason=(
                    "A short-lived load change can create transient shifts without a "
                    "persistent fault."
                ),
                confidence=confidence,
            )
        )

    if "increasing" in normalized and len(primary_observations) < 4:
        confidence = max(5, min(50, int(primary_confidence * 0.25)))
        alternatives.append(
            AlternativeHypothesis(
                title="Operating mode transition",
                reason=(
                    "Limited observation history can reflect a mode transition rather "
                    "than degradation."
                ),
                confidence=confidence,
            )
        )

    return tuple(alternatives[:2])


def _expected_outcome(*, assessment: str, recommendation: str, priority: str) -> str:
    normalized = assessment.casefold()
    if "increasing" in normalized or priority.casefold() == "high":
        return (
            "After investigation and corrective action, the driving signal should "
            "stabilize "
            "and return toward expected operating range."
        )
    if "stable" in normalized:
        return (
            "Maintain current operating conditions; expect continued stability with "
            "routine monitoring."
        )
    if "improving" in normalized:
        return (
            "Maintain current operations; expect the improving trend to continue if "
            "conditions remain unchanged."
        )
    return (
        f"Execute recommendation ({recommendation}) and verify the measured signal "
        "moves toward expected behavior."
    )

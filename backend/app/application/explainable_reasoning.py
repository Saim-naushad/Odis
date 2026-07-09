"""Deterministic explainability for reasoning outputs.

This module upgrades the platform from "a recommendation exists" to
"a recommendation exists *and we can explain why*".

No LLMs. No statistical models. The output is derived deterministically from the
same persisted reasoning artifacts the system already produces.

## Confidence algorithm (simple + auditable)

We compute confidence as a bounded score in [0, 100] from three signals:

- supporting observations: more samples generally increases confidence
- severity: higher priority recommendations imply stronger signal
- consistency: low variation and lack of contradictions imply stable evidence

Formula (all components are integers for stability):

base = 35
support = min(25, 8 * min(n_supporting, 3))          # up to +25
severity = {HIGH: +25, MEDIUM: +15, LOW: +5}         # up to +25
consistency = +15 if stable else +5                  # up to +15
penalties = -12 if contradictions else 0             # down to -12

confidence = clamp(base + support + severity + consistency + penalties, 0, 100)

Where:
- n_supporting is the number of observations for the primary measurement type
- stable is true when variation is low/medium (not "high") and trend is monotonic
  (we approximate monotonicity from the last 3 readings)
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.domain.reasoning import (
    AlternativeHypothesis,
    ConfidenceScore,
    Evidence,
)
from domain.entities.decision_plan import DecisionPlan
from domain.entities.observation import Observation


@dataclass(frozen=True, slots=True)
class ExplainableDecision:
    assessment: str
    evidence: tuple[Evidence, ...]
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
    evidence = _build_evidence(
        assessment=assessment,
        primary_observations=primary_observations,
        structured_assessment=structured_assessment,
        decision_plan=decision_plan,
    )
    confidence = _calculate_confidence(
        assessment=assessment,
        primary_observations=primary_observations,
        structured_assessment=structured_assessment,
        decision_plan=decision_plan,
    )
    alternatives = _build_alternatives(
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


def _build_evidence(
    *,
    assessment: str,
    primary_observations: list[Observation],
    structured_assessment: object | None,
    decision_plan: DecisionPlan,
) -> tuple[Evidence, ...]:
    _ = structured_assessment
    evidences: list[Evidence] = []
    raw_measurement_type = (
        primary_observations[0].measurement_type if primary_observations else "unknown"
    )
    measurement_type = str(getattr(raw_measurement_type, "name", raw_measurement_type))

    if primary_observations:
        latest = primary_observations[-1]
        evidences.append(
            Evidence(
                id="latest_reading",
                description="Latest recorded reading is considered in the decision.",
                measurement_type=measurement_type,
                observed_value=_format_observed_value(latest),
                contribution_weight=0.35,
            )
        )

    if len(primary_observations) >= 2:
        prev = primary_observations[-2]
        latest = primary_observations[-1]
        delta = latest.value - prev.value
        evidences.append(
            Evidence(
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
            Evidence(
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
        Evidence(
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

    # Ensure stable ordering for explainability and tests.
    return tuple(evidences)


def _calculate_confidence(
    *,
    assessment: str,
    primary_observations: list[Observation],
    structured_assessment: object | None,
    decision_plan: DecisionPlan,
) -> ConfidenceScore:
    contradictions = False
    variation_high = False

    # We intentionally keep this logic decoupled from internal class details so
    # the confidence layer remains stable even as the assessment model evolves.
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

    stable_recent = _is_monotonic_recent(primary_observations)
    stable = stable_recent and not variation_high
    consistency = 15 if stable else 5

    penalties = -12 if contradictions else 0

    base = 35
    raw = base + support + severity + consistency + penalties
    value = max(0, min(100, int(raw)))

    penalty_clause = (
        "Penalty -12 for contradictions."
        if contradictions
        else "No contradiction penalty."
    )
    rationale = (
        f"Base {base}. Support {support} from {n_supporting} observations. "
        f"Severity {severity} from {decision_plan.priority.value} priority. "
        f"Consistency {consistency} ({'stable' if stable else 'mixed'}). "
        f"{penalty_clause} "
        f"Assessment: {assessment}"
    )
    return ConfidenceScore(value=value, rationale=rationale)


def _is_monotonic_recent(primary_observations: list[Observation]) -> bool:
    if len(primary_observations) < 3:
        return True
    a, b, c = (
        primary_observations[-3],
        primary_observations[-2],
        primary_observations[-1],
    )
    inc = a.value <= b.value <= c.value
    dec = a.value >= b.value >= c.value
    return inc or dec


def _build_alternatives(
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

    # Alternative 1: sensor drift / measurement issue
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

    # Alternative 2: transient process / operating mode shift
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

    # Keep 1-2 deterministic alternatives.
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


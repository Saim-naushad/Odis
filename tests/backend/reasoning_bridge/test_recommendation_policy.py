"""Recommendation safety specification (PR178 spec sections 8, 9, 11, 12,
19 "Recommendation safety")."""

from __future__ import annotations

import inspect

from backend.app.application.reasoning_bridge.corroboration import (
    CorroborationOutcome,
)
from backend.app.application.reasoning_bridge.fault_class_mapping import (
    FaultClassMapping,
    get_fault_class_mapping,
)
from backend.app.application.reasoning_bridge.recommendation_policy import (
    build_recommendation,
)
from backend.app.domain.ai_fault_evidence import (
    AlertTransitionType,
    CorroborationResult,
    FaultRecommendation,
)

_MAPPING = get_fault_class_mapping("cooling_degradation")
_SENSOR_MAPPING = get_fault_class_mapping("sensor_anomaly")


def _recommendation(
    result: CorroborationResult,
    *,
    mapping: FaultClassMapping = _MAPPING,
    transition_type: AlertTransitionType = "confirmed",
) -> FaultRecommendation:
    corroboration = CorroborationOutcome(result, ("rule-1",), "notes", ("obs-1",))
    return build_recommendation(
        recommendation_id="rec-1",
        mapping=mapping,
        transition_type=transition_type,
        corroboration=corroboration,
    )


def test_corroborated_produces_actionable_recommendation() -> None:
    recommendation = _recommendation("corroborated")
    assert recommendation.status == "produced"
    assert recommendation.category == "investigate"
    assert recommendation.recommended_steps


def test_partially_corroborated_produces_verification_recommendation() -> None:
    recommendation = _recommendation("partially_corroborated")
    assert recommendation.status == "produced"
    assert recommendation.urgency == "INSPECTION_REQUIRED"


def test_not_corroborated_produces_no_fault_action_recommendation() -> None:
    recommendation = _recommendation("not_corroborated")
    assert recommendation.status == "withheld"
    assert recommendation.category == "monitor"


def test_insufficient_evidence_is_withheld_but_recorded() -> None:
    """Spec section 8: 'do not silently discard disagreement cases' —
    insufficient evidence still produces a `FaultRecommendation` record,
    just a withheld one."""
    recommendation = _recommendation("insufficient_evidence")
    assert recommendation.status == "withheld"
    assert recommendation.action_summary
    assert recommendation.reason


def test_recommendation_always_carries_supporting_evidence() -> None:
    for result in (
        "corroborated",
        "partially_corroborated",
        "not_corroborated",
        "insufficient_evidence",
    ):
        recommendation = _recommendation(result)
        assert recommendation.supporting_rule_ids == ("rule-1",)
        assert recommendation.supporting_observation_ids == ("obs-1",)
        assert recommendation.limitations


def test_sensor_anomaly_never_recommends_intervention_from_temperature_alone() -> None:
    recommendation = _recommendation("corroborated", mapping=_SENSOR_MAPPING)
    steps_text = " ".join(recommendation.recommended_steps).lower()
    forbidden_terms = ("shut down", "reduce load", "isolate", "trip")
    assert not any(term in steps_text for term in forbidden_terms)
    assert "redundant" in steps_text or "manual" in steps_text or "wiring" in steps_text


def test_urgency_is_not_derived_from_a_score_parameter() -> None:
    """Structural guarantee: `build_recommendation`'s signature has no
    score/probability parameter at all (spec section 12: "do not derive
    urgency solely from model score")."""
    parameters = inspect.signature(build_recommendation).parameters
    for name in parameters:
        assert "score" not in name
        assert "proba" not in name
        assert "confidence" not in name


def test_urgency_never_reaches_emergency_tier_without_a_deterministic_threshold() -> (
    None
):
    """This PR implements no duration/impact-based escalation, so no
    corroboration result should ever produce anything stronger than
    ELEVATED (spec section 12: avoid claiming emergency severity without
    a deterministic threshold)."""
    for result in (
        "corroborated",
        "partially_corroborated",
        "not_corroborated",
        "insufficient_evidence",
    ):
        recommendation = _recommendation(result)
        assert recommendation.urgency != "URGENT"

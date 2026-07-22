"""`fault_reasoning_result.v1` event specification (PR178 spec sections
14, 19 "Persistence and events")."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.application.reasoning_bridge.output_events import (
    build_reasoning_result_event,
)
from backend.app.domain.ai_fault_evidence import AiFaultEvidence, FaultRecommendation


def _evidence(**overrides: object) -> AiFaultEvidence:
    defaults: dict[str, object] = {
        "id": "evt-1",
        "source_event_id": "evt-1",
        "asset_id": "fuel-cell-stack-01",
        "observed_at": datetime(2026, 1, 1, tzinfo=UTC),
        "alert_transition_type": "confirmed",
        "diagnosed_fault_class": "cooling_degradation",
        "from_state": "healthy",
        "to_state": "confirmed_cooling_degradation",
        "model_system_version": "plant_alpha_fault_v1",
        "model_hash": "hash-a",
        "policy_hash": "policy-a",
        "feature_schema_version": "1.0",
        "class_scores": {"healthy": 0.05, "cooling_degradation": 0.9},
        "maximum_score": 0.9,
        "evidence_items": (),
        "investigation_id": "inv-1",
        "investigation_status": "OPEN",
        "previous_diagnosed_fault_class": None,
        "corroboration_result": "corroborated",
        "corroboration_rule_ids": ("rule-1",),
        "corroboration_notes": "notes",
        "recommendation": FaultRecommendation(
            id="rec-1",
            status="produced",
            category="investigate",
            urgency="ELEVATED",
            action_summary="summary",
            reason="reason",
            supporting_rule_ids=("rule-1",),
            supporting_observation_ids=("obs-1",),
            recommended_steps=("step-1",),
            limitations="limitations",
        ),
        "recorded_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return AiFaultEvidence(**defaults)  # type: ignore[arg-type]


def test_event_round_trips_expected_fields() -> None:
    event = build_reasoning_result_event(_evidence())
    payload = event.to_json_dict()

    assert payload["source_alert_event_id"] == "evt-1"
    assert payload["asset_id"] == "fuel-cell-stack-01"
    assert payload["diagnosed_class"] == "cooling_degradation"
    assert payload["corroboration_result"] == "corroborated"
    assert payload["investigation_id"] == "inv-1"
    assert payload["recommendation_status"] == "produced"
    assert payload["recommendation_action_summary"] == "summary"
    assert payload["urgency"] == "ELEVATED"
    assert payload["supporting_rule_ids"] == ["rule-1"]
    assert payload["supporting_observation_ids"] == ["obs-1"]
    assert payload["model_system_version"] == "plant_alpha_fault_v1"
    assert payload["model_hash"] == "hash-a"
    assert "reasoning_rule_version" in payload
    assert "event_id" in payload and payload["event_version"] == "v1"


def test_operational_situation_id_is_always_null() -> None:
    """This bridge never invokes the 7-stage ReasoningSession pipeline, so
    it never produces an OperationalSituation."""
    event = build_reasoning_result_event(_evidence())
    assert event.operational_situation_id is None


def test_event_never_carries_internal_hidden_state() -> None:
    payload = build_reasoning_result_event(_evidence()).to_json_dict()
    forbidden_keys = {
        "class_scores",
        "maximum_score",
        "evidence_items",
        "corroboration_notes",
        "feature_schema_version",
    }
    assert forbidden_keys.isdisjoint(payload)


def test_withheld_recommendation_has_null_action_fields() -> None:
    evidence = _evidence(
        corroboration_result="not_corroborated",
        recommendation=FaultRecommendation(
            id="rec-1",
            status="withheld",
            category="monitor",
            urgency="INFORMATIONAL",
            action_summary="no action",
            reason="reason",
            supporting_rule_ids=(),
            supporting_observation_ids=(),
            recommended_steps=("continue monitoring",),
            limitations="limitations",
        ),
    )
    payload = build_reasoning_result_event(evidence).to_json_dict()
    assert payload["recommendation_status"] == "withheld"
    assert payload["recommendation_action_summary"] == "no action"


def test_event_id_is_deterministic_for_identical_input() -> None:
    evidence = _evidence()
    first = build_reasoning_result_event(evidence)
    second = build_reasoning_result_event(evidence)
    assert first.event_id == second.event_id


def test_event_id_differs_for_different_investigation() -> None:
    first = build_reasoning_result_event(_evidence(investigation_id="inv-1"))
    second = build_reasoning_result_event(_evidence(investigation_id="inv-2"))
    assert first.event_id != second.event_id


def test_cleared_evidence_produces_event_with_no_recommendation() -> None:
    evidence = _evidence(
        alert_transition_type="cleared",
        corroboration_result="not_applicable",
        recommendation=None,
    )
    payload = build_reasoning_result_event(evidence).to_json_dict()
    assert payload["recommendation_status"] is None
    assert payload["recommendation_action_summary"] is None
    assert payload["urgency"] is None

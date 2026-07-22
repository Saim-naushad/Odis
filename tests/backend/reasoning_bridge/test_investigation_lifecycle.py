"""Investigation lifecycle decision specification (PR178 spec section
10, 19 "Lifecycle")."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.application.reasoning_bridge.investigation_lifecycle import (
    decide_investigation,
)
from backend.app.domain.ai_fault_evidence import AiFaultEvidence


def _evidence(
    *,
    investigation_id: str,
    investigation_status: str,
    diagnosed_fault_class: str,
) -> AiFaultEvidence:
    return AiFaultEvidence(
        id="evt-prev",
        source_event_id="evt-prev",
        asset_id="fuel-cell-stack-01",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        alert_transition_type="confirmed",
        diagnosed_fault_class=diagnosed_fault_class,
        from_state="healthy",
        to_state=f"confirmed_{diagnosed_fault_class}",
        model_system_version="v1",
        model_hash="hash",
        policy_hash="policy",
        feature_schema_version="1.0",
        class_scores={diagnosed_fault_class: 0.9},
        maximum_score=0.9,
        evidence_items=(),
        investigation_id=investigation_id,
        investigation_status=investigation_status,  # type: ignore[arg-type]
        previous_diagnosed_fault_class=None,
        corroboration_result="corroborated",
        corroboration_rule_ids=(),
        corroboration_notes="",
        recommendation=None,
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_first_confirmed_alert_creates_a_new_investigation() -> None:
    decision = decide_investigation(
        transition_type="confirmed",
        fault_class="cooling_degradation",
        active=None,
    )
    assert decision.is_new_investigation is True
    assert decision.investigation_status == "OPEN"
    assert decision.previous_diagnosed_fault_class is None
    assert decision.investigation_id


def test_class_changed_reuses_the_active_investigation_id() -> None:
    active = _evidence(
        investigation_id="inv-1",
        investigation_status="OPEN",
        diagnosed_fault_class="cooling_degradation",
    )
    decision = decide_investigation(
        transition_type="class_changed",
        fault_class="hydrogen_supply_issue",
        active=active,
    )
    assert decision.investigation_id == "inv-1"
    assert decision.is_new_investigation is False
    assert decision.investigation_status == "OPEN"
    assert decision.previous_diagnosed_fault_class == "cooling_degradation"


def test_cleared_marks_the_active_investigation_closed() -> None:
    active = _evidence(
        investigation_id="inv-1",
        investigation_status="OPEN",
        diagnosed_fault_class="cooling_degradation",
    )
    decision = decide_investigation(
        transition_type="cleared",
        fault_class="cooling_degradation",
        active=active,
    )
    assert decision.investigation_id == "inv-1"
    assert decision.investigation_status == "CLEARED"
    assert decision.is_new_investigation is False


def test_new_confirmed_alert_after_clear_creates_a_new_occurrence() -> None:
    active = _evidence(
        investigation_id="inv-1",
        investigation_status="CLEARED",
        diagnosed_fault_class="cooling_degradation",
    )
    decision = decide_investigation(
        transition_type="confirmed",
        fault_class="cooling_degradation",
        active=active,
    )
    assert decision.investigation_id != "inv-1"
    assert decision.is_new_investigation is True
    assert decision.investigation_status == "OPEN"


def test_repeated_confirmed_for_same_class_is_not_treated_as_new() -> None:
    """Idempotent-replay-adjacent case: a second `confirmed`-type call
    for an asset that already has an OPEN investigation of the same
    class reuses that investigation rather than minting a second one —
    in practice PR177 never re-emits `confirmed` for an already-open
    alert, but this must not crash or fork state if it ever did."""
    active = _evidence(
        investigation_id="inv-1",
        investigation_status="OPEN",
        diagnosed_fault_class="cooling_degradation",
    )
    decision = decide_investigation(
        transition_type="confirmed",
        fault_class="cooling_degradation",
        active=active,
    )
    assert decision.investigation_id == "inv-1"
    assert decision.is_new_investigation is False
    assert decision.previous_diagnosed_fault_class is None


def test_cleared_with_no_active_investigation_is_recorded_not_dropped() -> None:
    """Defensive path: a `cleared` event with no active OPEN investigation
    on record (e.g. after a worker restart) is still recorded as its own
    (immediately closed) occurrence rather than silently ignored."""
    decision = decide_investigation(
        transition_type="cleared",
        fault_class="cooling_degradation",
        active=None,
    )
    assert decision.investigation_status == "CLEARED"
    assert decision.investigation_id

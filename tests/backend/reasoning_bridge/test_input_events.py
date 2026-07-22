"""`validate_alert_transition` specification (PR178 spec sections 3, 19
"Event validation").

Structural validation (event version, required fields, timestamp,
transition type, scores, and the `healthy` rejection) lives here.
Semantic fault-class support (only `cooling_degradation`/
`hydrogen_supply_issue`/`sensor_anomaly`) is enforced one layer up, in
`fault_class_mapping.is_supported_fault_class` /
`ReasoningBridgeService` — see `test_reasoning_bridge_service.py`'s
`test_unsupported_fault_class_is_rejected`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.application.reasoning_bridge.input_events import (
    AlertTransitionValidationError,
    HealthyClassRejectedError,
    MalformedScoresError,
    MalformedStateError,
    MalformedTimestampError,
    MissingFieldError,
    UnsupportedEventVersionError,
    UnsupportedTransitionTypeError,
    validate_alert_transition,
)

_VALID_RAW: dict[str, object] = {
    "event_id": "evt-1",
    "event_version": "v1",
    "occurred_at": "2026-01-01T00:00:05+00:00",
    "asset_id": "fuel-cell-stack-01",
    "source_timestamp": "2026-01-01T00:00:00+00:00",
    "transition_type": "confirmed",
    "from_state": "healthy",
    "to_state": "confirmed_cooling_degradation",
    "diagnosed_class": "cooling_degradation",
    "evidence": [{"label": "top_class_probability", "value": 0.9, "detail": "x"}],
    "model_system_version": "plant_alpha_fault_v1",
    "model_hash": "hash-a",
    "policy_hash": "policy-a",
    "feature_schema_version": "1.0",
    "class_scores": {"healthy": 0.05, "cooling_degradation": 0.9},
    "maximum_score": 0.9,
}


def test_valid_confirmed_transition_is_accepted() -> None:
    event = validate_alert_transition(dict(_VALID_RAW))
    assert event.asset_id == "fuel-cell-stack-01"
    assert event.transition_type == "confirmed"
    assert event.fault_class == "cooling_degradation"
    assert event.diagnosed_class == "cooling_degradation"
    assert event.class_scores == {"healthy": 0.05, "cooling_degradation": 0.9}
    assert event.maximum_score == 0.9
    assert event.source_timestamp == datetime(2026, 1, 1, tzinfo=UTC)


def test_valid_class_changed_transition_is_accepted() -> None:
    raw = {
        **_VALID_RAW,
        "transition_type": "class_changed",
        "from_state": "confirmed_cooling_degradation",
        "to_state": "confirmed_hydrogen_supply_issue",
        "diagnosed_class": "hydrogen_supply_issue",
    }
    event = validate_alert_transition(raw)
    assert event.fault_class == "hydrogen_supply_issue"


def test_valid_cleared_transition_extracts_class_from_from_state() -> None:
    raw = {
        **_VALID_RAW,
        "transition_type": "cleared",
        "from_state": "confirmed_sensor_anomaly",
        "to_state": "healthy",
        "diagnosed_class": "healthy",
    }
    event = validate_alert_transition(raw)
    assert event.fault_class == "sensor_anomaly"
    assert event.transition_type == "cleared"


def test_unsupported_event_version_is_rejected() -> None:
    raw = {**_VALID_RAW, "event_version": "v2"}
    with pytest.raises(UnsupportedEventVersionError):
        validate_alert_transition(raw)


def test_unsupported_transition_type_is_rejected() -> None:
    raw = {**_VALID_RAW, "transition_type": "warming_up"}
    with pytest.raises(UnsupportedTransitionTypeError):
        validate_alert_transition(raw)


def test_malformed_timestamp_is_rejected() -> None:
    raw = {**_VALID_RAW, "source_timestamp": "not-a-timestamp"}
    with pytest.raises(MalformedTimestampError):
        validate_alert_transition(raw)


@pytest.mark.parametrize(
    "missing_field", sorted(set(_VALID_RAW) - {"occurred_at"})
)
def test_missing_required_field_is_rejected(missing_field: str) -> None:
    """`occurred_at` is present in a real published event but is not part
    of this validator's own required-field contract (`ValidatedAlertTransition`
    has no `occurred_at` field — only `source_timestamp` is used)."""
    raw = {k: v for k, v in _VALID_RAW.items() if k != missing_field}
    with pytest.raises(MissingFieldError):
        validate_alert_transition(raw)


def test_malformed_class_scores_type_is_rejected() -> None:
    raw = {**_VALID_RAW, "class_scores": "not-a-dict"}
    with pytest.raises(MalformedScoresError):
        validate_alert_transition(raw)


def test_empty_class_scores_is_rejected() -> None:
    raw = {**_VALID_RAW, "class_scores": {}}
    with pytest.raises(MalformedScoresError):
        validate_alert_transition(raw)


def test_non_numeric_class_score_is_rejected() -> None:
    raw = {**_VALID_RAW, "class_scores": {"healthy": "not-a-number"}}
    with pytest.raises(MalformedScoresError):
        validate_alert_transition(raw)


def test_non_finite_maximum_score_is_rejected() -> None:
    raw = {**_VALID_RAW, "maximum_score": float("nan")}
    with pytest.raises(MalformedScoresError):
        validate_alert_transition(raw)


def test_out_of_range_maximum_score_is_rejected() -> None:
    raw = {**_VALID_RAW, "maximum_score": 1.5}
    with pytest.raises(MalformedScoresError):
        validate_alert_transition(raw)


def test_missing_hashes_or_version_is_rejected() -> None:
    for field_name in (
        "model_system_version",
        "model_hash",
        "policy_hash",
        "feature_schema_version",
    ):
        raw = {**_VALID_RAW, field_name: None}
        with pytest.raises(MissingFieldError):
            validate_alert_transition(raw)


def test_healthy_class_is_rejected() -> None:
    raw = {
        **_VALID_RAW,
        "from_state": "confirmed_cooling_degradation",
        "to_state": "confirmed_healthy",
    }
    with pytest.raises(HealthyClassRejectedError):
        validate_alert_transition(raw)


def test_malformed_state_without_confirmed_prefix_is_rejected() -> None:
    raw = {**_VALID_RAW, "to_state": "cooling_degradation"}
    with pytest.raises(MalformedStateError):
        validate_alert_transition(raw)


def test_validate_never_raises_a_bare_exception() -> None:
    malformed_inputs = [
        {},
        {**_VALID_RAW, "asset_id": ""},
        {**_VALID_RAW, "asset_id": None},
        {**_VALID_RAW, "evidence": "not-a-list"},
    ]
    for raw in malformed_inputs:
        with pytest.raises(AlertTransitionValidationError):
            validate_alert_transition(raw)

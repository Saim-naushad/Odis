"""Input-event validation and output-event serialization (PR177 spec
sections 3, 6, 8, 17 "Input validation" / "Event serialization")."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.simulator.inference.result import (
    EvidenceItem,
    InferenceResult,
    InferenceStatus,
)
from backend.simulator.inference_worker.events import (
    MalformedTimestampError,
    MissingFieldError,
    NonFiniteValueError,
    UnitMismatchError,
    UnsupportedEventVersionError,
    UnsupportedMeasurementNameError,
    build_data_quality_event,
    build_result_event,
    build_transition_event,
    validate_telemetry_event,
)

_VALID_RAW: dict[str, object] = {
    "event_id": "evt-1",
    "event_version": "v1",
    "asset_id": "fuel-cell-stack-01",
    "timestamp": "2026-01-01T00:00:00+00:00",
    "measurement_name": "stack_temperature",
    "value": 65.0,
    "unit": "celsius",
    "source": "plant-alpha-simulator",
}


# --- Input validation -------------------------------------------------------


def test_valid_canonical_event_is_accepted() -> None:
    event = validate_telemetry_event(dict(_VALID_RAW))
    assert event.asset_id == "fuel-cell-stack-01"
    assert event.measurement_name == "stack_temperature"
    assert event.value == 65.0
    assert event.timestamp == datetime(2026, 1, 1, tzinfo=UTC)


def test_unsupported_event_version_is_rejected() -> None:
    raw = {**_VALID_RAW, "event_version": "v2"}
    with pytest.raises(UnsupportedEventVersionError):
        validate_telemetry_event(raw)


def test_malformed_timestamp_is_rejected() -> None:
    raw = {**_VALID_RAW, "timestamp": "not-a-timestamp"}
    with pytest.raises(MalformedTimestampError):
        validate_telemetry_event(raw)


def test_bad_unit_is_rejected() -> None:
    raw = {**_VALID_RAW, "unit": "fahrenheit"}
    with pytest.raises(UnitMismatchError):
        validate_telemetry_event(raw)


def test_non_finite_value_is_rejected() -> None:
    raw = {**_VALID_RAW, "value": float("nan")}
    with pytest.raises(NonFiniteValueError):
        validate_telemetry_event(raw)


def test_infinite_value_is_rejected() -> None:
    raw = {**_VALID_RAW, "value": float("inf")}
    with pytest.raises(NonFiniteValueError):
        validate_telemetry_event(raw)


def test_non_numeric_value_is_rejected() -> None:
    raw = {**_VALID_RAW, "value": "not-a-number"}
    with pytest.raises(NonFiniteValueError):
        validate_telemetry_event(raw)


def test_unknown_measurement_is_rejected() -> None:
    raw = {**_VALID_RAW, "measurement_name": "warp_core_temperature"}
    with pytest.raises(UnsupportedMeasurementNameError):
        validate_telemetry_event(raw)


@pytest.mark.parametrize("missing_field", sorted(_VALID_RAW))
def test_missing_required_field_is_rejected(missing_field: str) -> None:
    raw = {k: v for k, v in _VALID_RAW.items() if k != missing_field}
    with pytest.raises(MissingFieldError):
        validate_telemetry_event(raw)


def test_validate_never_raises_a_bare_exception() -> None:
    """Every rejection path raises a `TelemetryEventValidationError`
    subclass — never an unrelated `KeyError`/`TypeError` that would
    escape the worker's handling and crash it."""
    from backend.simulator.inference_worker.events import (
        TelemetryEventValidationError,
    )

    malformed_inputs = [
        {},
        {**_VALID_RAW, "asset_id": ""},
        {**_VALID_RAW, "asset_id": None},
        {**_VALID_RAW, "value": None},
        {**_VALID_RAW, "value": True},
    ]
    for raw in malformed_inputs:
        with pytest.raises(TelemetryEventValidationError):
            validate_telemetry_event(raw)


# --- Output event construction / serialization ------------------------------


def _result(**overrides: object) -> InferenceResult:
    defaults: dict[str, object] = {
        "status": InferenceStatus.VALID_PREDICTION,
        "asset_id": "fuel-cell-stack-01",
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "diagnosed_class": "cooling_degradation",
        "class_probabilities": {"healthy": 0.1, "cooling_degradation": 0.9},
        "maximum_probability": 0.9,
        "alert_state": "confirmed_cooling_degradation",
        "alert_event": None,
        "evidence": (
            EvidenceItem(label="top_class_probability", value=0.9, detail="x"),
        ),
        "model_system_version": "v1",
        "model_hash": "hash-a",
        "policy_hash": "policy-a",
        "feature_schema_version": "schema-1",
    }
    defaults.update(overrides)
    return InferenceResult(**defaults)  # type: ignore[arg-type]


def test_result_event_round_trips_and_omits_forbidden_fields() -> None:
    result = _result()
    event = build_result_event(result)
    payload = event.to_json_dict()

    assert payload["status"] == "valid_prediction"
    assert payload["diagnosed_class"] == "cooling_degradation"
    assert payload["model_hash"] == "hash-a"
    assert payload["policy_hash"] == "policy-a"
    assert payload["feature_schema_version"] == "schema-1"
    assert "event_id" in payload and payload["event_version"] == "v1"
    forbidden = {
        "fault_label",
        "scenario_name",
        "configured_severity",
        "dataset_id",
        "simulation_run_id",
        "split",
    }
    assert forbidden.isdisjoint(payload)


def test_result_event_class_order_and_scores_are_stable() -> None:
    result = _result()
    first = build_result_event(result).to_json_dict()
    second = build_result_event(result).to_json_dict()
    assert first["class_scores"] == second["class_scores"]
    assert list(first["class_scores"]) == list(second["class_scores"])


def test_result_event_id_is_deterministic_for_identical_input() -> None:
    result = _result()
    first = build_result_event(result)
    second = build_result_event(result)
    assert first.event_id == second.event_id


def test_result_event_id_differs_for_different_status() -> None:
    warming_up = _result(
        status=InferenceStatus.WARMING_UP,
        diagnosed_class=None,
        class_probabilities=None,
        maximum_probability=None,
        alert_state=None,
        samples_available=3,
        samples_required=12,
    )
    valid = _result()
    assert build_result_event(warming_up).event_id != build_result_event(valid).event_id


def test_transition_event_is_none_without_alert_event() -> None:
    result = _result(alert_event=None)
    assert build_transition_event(result) is None


def test_transition_event_built_from_alert_event() -> None:
    result = _result(
        alert_event={
            "elapsed_sim_seconds": 120.0,
            "event_type": "new_alert",
            "from_state": "healthy",
            "to_state": "confirmed_cooling_degradation",
            "fault_class": "cooling_degradation",
        }
    )
    event = build_transition_event(result)
    assert event is not None
    assert event.transition_type == "confirmed"
    assert event.from_state == "healthy"
    assert event.to_state == "confirmed_cooling_degradation"
    assert event.diagnosed_class == "cooling_degradation"


@pytest.mark.parametrize(
    ("alert_event_type", "expected_transition_type"),
    [
        ("new_alert", "confirmed"),
        ("class_change", "class_changed"),
        ("cleared", "cleared"),
    ],
)
def test_transition_type_mapping(
    alert_event_type: str, expected_transition_type: str
) -> None:
    result = _result(
        alert_event={
            "elapsed_sim_seconds": 1.0,
            "event_type": alert_event_type,
            "from_state": "a",
            "to_state": "b",
            "fault_class": "cooling_degradation",
        }
    )
    event = build_transition_event(result)
    assert event is not None
    assert event.transition_type == expected_transition_type


def test_transition_event_id_is_deterministic() -> None:
    alert_event = {
        "elapsed_sim_seconds": 1.0,
        "event_type": "new_alert",
        "from_state": "healthy",
        "to_state": "confirmed_cooling_degradation",
        "fault_class": "cooling_degradation",
    }
    result = _result(alert_event=alert_event)
    first = build_transition_event(result)
    second = build_transition_event(result)
    assert first is not None and second is not None
    assert first.event_id == second.event_id


def test_data_quality_event_round_trips_and_id_is_deterministic() -> None:
    kwargs = {
        "asset_id": "fuel-cell-stack-01",
        "source_timestamp": datetime(2026, 1, 1, tzinfo=UTC),
        "reason": "late",
        "detail": "timestamp does not follow the last processed sample",
    }
    first = build_data_quality_event(**kwargs)  # type: ignore[arg-type]
    second = build_data_quality_event(**kwargs)  # type: ignore[arg-type]
    assert first.event_id == second.event_id
    payload = first.to_json_dict()
    assert payload["reason"] == "late"
    assert payload["asset_id"] == "fuel-cell-stack-01"

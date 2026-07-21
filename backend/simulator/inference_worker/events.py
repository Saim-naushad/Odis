"""Versioned Kafka event contracts (PR177 spec sections 3 and 8).

Input: `TelemetryObservationEventV1` — one canonical measurement reading,
matching the MQTT publisher's existing per-measurement granularity
(`backend.simulator.publishers.mqtt_publisher`) and reusing this
codebase's own canonical measurement/unit vocabulary
(`backend.simulator.inference.telemetry`) rather than redeclaring it.

Output: `FaultInferenceResultEventV1` (`fault_inference.v1`) and
`FaultAlertTransitionEventV1` (`fault_alert_transition.v1`), built from
`backend.simulator.inference.result.InferenceResult` — the promoted
runtime's own output type, never re-derived independently. `event_id` is
deterministic (`identity.deterministic_event_id`) for both, so a replayed
input maps to the same downstream event.

`TelemetryDataQualityEventV1` differentiates ingestion/data-quality
failures (malformed, incomplete, conflicting, late — spec section 10)
from `insufficient_data`, which is a valid *inference-runtime* outcome
carried on `FaultInferenceResultEventV1` instead, never on this type.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.simulator.inference.result import InferenceResult
from backend.simulator.inference.telemetry import (
    CANONICAL_UNITS,
    SUPPORTED_MEASUREMENTS,
)
from backend.simulator.inference_worker.identity import deterministic_event_id

INPUT_EVENT_VERSION = "v1"
RESULT_EVENT_TYPE = "fault_inference.v1"
TRANSITION_EVENT_TYPE = "fault_alert_transition.v1"

SUPPORTED_INPUT_EVENT_VERSIONS = frozenset({INPUT_EVENT_VERSION})

_REQUIRED_INPUT_FIELDS = (
    "event_id",
    "event_version",
    "asset_id",
    "timestamp",
    "measurement_name",
    "value",
    "unit",
    "source",
)

_TRANSITION_TYPE_BY_ALERT_EVENT_TYPE = {
    "new_alert": "confirmed",
    "class_change": "class_changed",
    "cleared": "cleared",
}


class TelemetryEventValidationError(Exception):
    """Base class for input-event validation failures. `reason_code` is a
    stable, low-cardinality string used for both the data-quality event's
    `reason` and the `telemetry_malformed` metric label."""

    reason_code = "malformed"


class MissingFieldError(TelemetryEventValidationError):
    def __init__(self, field_name: str) -> None:
        super().__init__(f"telemetry event is missing required field {field_name!r}")
        self.field_name = field_name


class UnsupportedEventVersionError(TelemetryEventValidationError):
    def __init__(self, event_version: object) -> None:
        super().__init__(
            f"unsupported event_version {event_version!r} "
            f"(supported: {sorted(SUPPORTED_INPUT_EVENT_VERSIONS)})"
        )


class MalformedTimestampError(TelemetryEventValidationError):
    def __init__(self, raw: object) -> None:
        super().__init__(f"telemetry event has an unparseable timestamp: {raw!r}")


class UnsupportedMeasurementNameError(TelemetryEventValidationError):
    def __init__(self, measurement_name: object) -> None:
        super().__init__(f"unsupported measurement_name: {measurement_name!r}")


class UnitMismatchError(TelemetryEventValidationError):
    def __init__(self, measurement_name: str, actual: object, expected: str) -> None:
        super().__init__(
            f"measurement {measurement_name!r} has unit {actual!r}, expected "
            f"the canonical unit {expected!r}"
        )


class NonFiniteValueError(TelemetryEventValidationError):
    def __init__(self, measurement_name: str, value: object) -> None:
        super().__init__(
            f"non-finite telemetry value for {measurement_name!r}: {value!r}"
        )


class InvalidAssetIdError(TelemetryEventValidationError):
    def __init__(self) -> None:
        super().__init__("telemetry event has an empty asset_id")


@dataclass(frozen=True)
class TelemetryObservationEventV1:
    """One validated canonical measurement reading."""

    event_id: str
    event_version: str
    asset_id: str
    timestamp: datetime
    measurement_name: str
    value: float
    unit: str
    source: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_version": self.event_version,
            "asset_id": self.asset_id,
            "timestamp": self.timestamp.isoformat(),
            "measurement_name": self.measurement_name,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
        }


def validate_telemetry_event(raw: dict[str, Any]) -> TelemetryObservationEventV1:
    """Validate a raw decoded input-topic message. Never raises anything
    other than a `TelemetryEventValidationError` subclass — malformed
    input must never crash the worker (spec section 3)."""
    for field_name in _REQUIRED_INPUT_FIELDS:
        if field_name not in raw or raw[field_name] is None:
            raise MissingFieldError(field_name)

    event_version = raw["event_version"]
    if event_version not in SUPPORTED_INPUT_EVENT_VERSIONS:
        raise UnsupportedEventVersionError(event_version)

    asset_id = raw["asset_id"]
    if not isinstance(asset_id, str) or not asset_id:
        raise InvalidAssetIdError()

    timestamp = _parse_timestamp(raw["timestamp"])

    measurement_name = raw["measurement_name"]
    if measurement_name not in SUPPORTED_MEASUREMENTS:
        raise UnsupportedMeasurementNameError(measurement_name)

    unit = raw["unit"]
    expected_unit = CANONICAL_UNITS[measurement_name]
    if unit != expected_unit:
        raise UnitMismatchError(measurement_name, unit, expected_unit)

    value = raw["value"]
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise NonFiniteValueError(measurement_name, value)
    value = float(value)
    if not math.isfinite(value):
        raise NonFiniteValueError(measurement_name, value)

    return TelemetryObservationEventV1(
        event_id=str(raw["event_id"]),
        event_version=str(event_version),
        asset_id=asset_id,
        timestamp=timestamp,
        measurement_name=measurement_name,
        value=value,
        unit=unit,
        source=str(raw["source"]),
    )


def _parse_timestamp(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise MalformedTimestampError(raw)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MalformedTimestampError(raw) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


@dataclass(frozen=True)
class FaultInferenceResultEventV1:
    """`fault_inference.v1` — one per successfully assembled sample,
    regardless of `status` (spec section 8)."""

    event_id: str
    event_version: str
    occurred_at: datetime
    asset_id: str
    source_timestamp: datetime
    status: str
    diagnosed_class: str | None = None
    class_scores: dict[str, float] | None = None
    maximum_score: float | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    alert_state: str | None = None
    model_system_version: str | None = None
    model_hash: str | None = None
    policy_hash: str | None = None
    feature_schema_version: str | None = None
    reason_codes: list[str] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat(),
            "asset_id": self.asset_id,
            "source_timestamp": self.source_timestamp.isoformat(),
            "status": self.status,
            "diagnosed_class": self.diagnosed_class,
            "class_scores": self.class_scores,
            "maximum_score": self.maximum_score,
            "evidence": self.evidence,
            "alert_state": self.alert_state,
            "model_system_version": self.model_system_version,
            "model_hash": self.model_hash,
            "policy_hash": self.policy_hash,
            "feature_schema_version": self.feature_schema_version,
            "reason_codes": self.reason_codes,
        }


def build_result_event(
    result: InferenceResult, *, now: datetime | None = None
) -> FaultInferenceResultEventV1:
    occurred_at = now or datetime.now(UTC)
    event_id = deterministic_event_id(
        RESULT_EVENT_TYPE,
        result.asset_id,
        result.timestamp.isoformat(),
        result.model_hash or "",
        result.status.value,
    )
    return FaultInferenceResultEventV1(
        event_id=event_id,
        event_version=INPUT_EVENT_VERSION,
        occurred_at=occurred_at,
        asset_id=result.asset_id,
        source_timestamp=result.timestamp,
        status=result.status.value,
        diagnosed_class=result.diagnosed_class,
        class_scores=result.class_probabilities,
        maximum_score=result.maximum_probability,
        evidence=[item.to_json_dict() for item in result.evidence],
        alert_state=result.alert_state,
        model_system_version=result.model_system_version,
        model_hash=result.model_hash,
        policy_hash=result.policy_hash,
        feature_schema_version=result.feature_schema_version,
        reason_codes=list(result.reason_codes),
    )


@dataclass(frozen=True)
class FaultAlertTransitionEventV1:
    """`fault_alert_transition.v1` — published only when
    `InferenceResult.alert_event` is present (spec section 8: "do not
    emit a new alert-transition event for every confirmed row")."""

    event_id: str
    event_version: str
    occurred_at: datetime
    asset_id: str
    source_timestamp: datetime
    transition_type: str
    from_state: str
    to_state: str
    diagnosed_class: str | None
    evidence: list[dict[str, Any]]
    model_system_version: str | None
    model_hash: str | None
    policy_hash: str | None

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat(),
            "asset_id": self.asset_id,
            "source_timestamp": self.source_timestamp.isoformat(),
            "transition_type": self.transition_type,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "diagnosed_class": self.diagnosed_class,
            "evidence": self.evidence,
            "model_system_version": self.model_system_version,
            "model_hash": self.model_hash,
            "policy_hash": self.policy_hash,
        }


def build_transition_event(
    result: InferenceResult, *, now: datetime | None = None
) -> FaultAlertTransitionEventV1 | None:
    if result.alert_event is None:
        return None
    alert_event = result.alert_event
    transition_type = _TRANSITION_TYPE_BY_ALERT_EVENT_TYPE[alert_event["event_type"]]
    occurred_at = now or datetime.now(UTC)
    event_id = deterministic_event_id(
        TRANSITION_EVENT_TYPE,
        result.asset_id,
        result.timestamp.isoformat(),
        transition_type,
        str(alert_event["fault_class"]),
        result.model_hash or "",
    )
    return FaultAlertTransitionEventV1(
        event_id=event_id,
        event_version=INPUT_EVENT_VERSION,
        occurred_at=occurred_at,
        asset_id=result.asset_id,
        source_timestamp=result.timestamp,
        transition_type=transition_type,
        from_state=str(alert_event["from_state"]),
        to_state=str(alert_event["to_state"]),
        diagnosed_class=result.diagnosed_class,
        evidence=[item.to_json_dict() for item in result.evidence],
        model_system_version=result.model_system_version,
        model_hash=result.model_hash,
        policy_hash=result.policy_hash,
    )


@dataclass(frozen=True)
class TelemetryDataQualityEventV1:
    """Structured outcome for ingestion-layer failures — malformed,
    incomplete (timeout), conflicting duplicate, or late (spec section
    10). Never used for `insufficient_data`, which is a
    `FaultInferenceResultEventV1` status instead."""

    event_id: str
    event_version: str
    occurred_at: datetime
    asset_id: str | None
    source_timestamp: datetime | None
    reason: str
    detail: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat(),
            "asset_id": self.asset_id,
            "source_timestamp": (
                self.source_timestamp.isoformat() if self.source_timestamp else None
            ),
            "reason": self.reason,
            "detail": self.detail,
        }


def build_data_quality_event(
    *,
    asset_id: str | None,
    source_timestamp: datetime | None,
    reason: str,
    detail: str,
    now: datetime | None = None,
) -> TelemetryDataQualityEventV1:
    occurred_at = now or datetime.now(UTC)
    event_id = deterministic_event_id(
        "telemetry_data_quality.v1",
        asset_id or "",
        source_timestamp.isoformat() if source_timestamp else "",
        reason,
        detail,
    )
    return TelemetryDataQualityEventV1(
        event_id=event_id,
        event_version=INPUT_EVENT_VERSION,
        occurred_at=occurred_at,
        asset_id=asset_id,
        source_timestamp=source_timestamp,
        reason=reason,
        detail=detail,
    )

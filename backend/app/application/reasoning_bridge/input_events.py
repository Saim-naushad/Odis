"""Validated input contract: PR177's `fault_alert_transition.v1` (spec
section 3).

`validate_alert_transition` never raises anything other than an
`AlertTransitionValidationError` subclass — malformed events must not
enter reasoning (and must not crash the worker). Only `confirmed`,
`class_changed`, and `cleared` transitions are accepted; `healthy` is
never accepted as a fault class (spec section 6: "do not map healthy
into a fault investigation").
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

SUPPORTED_INPUT_EVENT_VERSIONS = frozenset({"v1"})
SUPPORTED_TRANSITION_TYPES = frozenset({"confirmed", "class_changed", "cleared"})
_CONFIRMED_PREFIX = "confirmed_"

_REQUIRED_FIELDS = (
    "event_id",
    "event_version",
    "asset_id",
    "source_timestamp",
    "transition_type",
    "from_state",
    "to_state",
    "diagnosed_class",
    "evidence",
    "model_system_version",
    "model_hash",
    "policy_hash",
    "feature_schema_version",
    "class_scores",
    "maximum_score",
)


class AlertTransitionValidationError(Exception):
    """Base class for input-event validation failures — never anything
    else escapes `validate_alert_transition`."""

    reason_code = "malformed"


class MissingFieldError(AlertTransitionValidationError):
    def __init__(self, field_name: str) -> None:
        super().__init__(f"alert-transition event is missing field {field_name!r}")
        self.field_name = field_name


class UnsupportedEventVersionError(AlertTransitionValidationError):
    def __init__(self, event_version: object) -> None:
        super().__init__(
            f"unsupported event_version {event_version!r} "
            f"(supported: {sorted(SUPPORTED_INPUT_EVENT_VERSIONS)})"
        )


class UnsupportedTransitionTypeError(AlertTransitionValidationError):
    def __init__(self, transition_type: object) -> None:
        super().__init__(
            f"unsupported transition_type {transition_type!r} "
            f"(supported: {sorted(SUPPORTED_TRANSITION_TYPES)})"
        )


class MalformedTimestampError(AlertTransitionValidationError):
    def __init__(self, raw: object) -> None:
        super().__init__(f"unparseable source_timestamp: {raw!r}")


class MalformedScoresError(AlertTransitionValidationError):
    def __init__(self, detail: str) -> None:
        super().__init__(f"malformed class_scores/maximum_score: {detail}")


class HealthyClassRejectedError(AlertTransitionValidationError):
    """Raised when `diagnosed_class`/the transition's subject class is
    ``healthy`` — never a fault investigation subject."""

    reason_code = "healthy_class_rejected"

    def __init__(self) -> None:
        super().__init__("healthy is never accepted as a fault-alert class")


class MalformedStateError(AlertTransitionValidationError):
    def __init__(self, transition_type: str, from_state: str, to_state: str) -> None:
        super().__init__(
            f"cannot extract a fault class from transition_type={transition_type!r} "
            f"from_state={from_state!r} to_state={to_state!r}"
        )


@dataclass(frozen=True)
class ValidatedAlertTransition:
    """A structurally valid `fault_alert_transition.v1` event, with the
    authoritative subject fault class already extracted.

    `fault_class` is parsed from the FSM's own `confirmed_<class>` state
    string (`to_state` for confirmed/class_changed, `from_state` for
    cleared) rather than trusted from `diagnosed_class` — `diagnosed_class`
    is merely *this row's* raw model output, which need not equal the
    class the alert-policy state machine is actually transitioning
    (e.g. a `cleared` row's own diagnosis is usually, but not
    structurally guaranteed to be, ``healthy``). See
    `backend.simulator.dataset.alert_policy.state_machine`'s
    `_confirmed_state` helper — states are always literally
    ``f"confirmed_{fault_class}"``.
    """

    event_id: str
    event_version: str
    asset_id: str
    source_timestamp: datetime
    transition_type: str
    from_state: str
    to_state: str
    fault_class: str
    diagnosed_class: str
    evidence_items: tuple[dict[str, Any], ...]
    model_system_version: str
    model_hash: str
    policy_hash: str
    feature_schema_version: str
    class_scores: dict[str, float]
    maximum_score: float


def validate_alert_transition(raw: dict[str, Any]) -> ValidatedAlertTransition:
    for field_name in _REQUIRED_FIELDS:
        if field_name not in raw or raw[field_name] is None:
            raise MissingFieldError(field_name)

    event_version = raw["event_version"]
    if event_version not in SUPPORTED_INPUT_EVENT_VERSIONS:
        raise UnsupportedEventVersionError(event_version)

    transition_type = raw["transition_type"]
    if transition_type not in SUPPORTED_TRANSITION_TYPES:
        raise UnsupportedTransitionTypeError(transition_type)

    asset_id = raw["asset_id"]
    if not isinstance(asset_id, str) or not asset_id:
        raise MissingFieldError("asset_id")

    source_timestamp = _parse_timestamp(raw["source_timestamp"])

    from_state = str(raw["from_state"])
    to_state = str(raw["to_state"])
    fault_class = _extract_fault_class(transition_type, from_state, to_state)
    if fault_class == "healthy":
        raise HealthyClassRejectedError()

    diagnosed_class = str(raw["diagnosed_class"])

    evidence = raw["evidence"]
    if not isinstance(evidence, list):
        raise MalformedScoresError("evidence must be a list")

    class_scores = raw["class_scores"]
    if not isinstance(class_scores, dict) or not class_scores:
        raise MalformedScoresError("class_scores must be a non-empty object")
    for score in class_scores.values():
        if not isinstance(score, int | float) or isinstance(score, bool):
            raise MalformedScoresError("class_scores values must be numeric")
        if not math.isfinite(float(score)):
            raise MalformedScoresError("class_scores values must be finite")

    maximum_score = raw["maximum_score"]
    if not isinstance(maximum_score, int | float) or isinstance(maximum_score, bool):
        raise MalformedScoresError("maximum_score must be numeric")
    maximum_score = float(maximum_score)
    if not math.isfinite(maximum_score) or not 0.0 <= maximum_score <= 1.0:
        raise MalformedScoresError("maximum_score must be finite and in [0.0, 1.0]")

    return ValidatedAlertTransition(
        event_id=str(raw["event_id"]),
        event_version=str(event_version),
        asset_id=asset_id,
        source_timestamp=source_timestamp,
        transition_type=str(transition_type),
        from_state=from_state,
        to_state=to_state,
        fault_class=fault_class,
        diagnosed_class=diagnosed_class,
        evidence_items=tuple(evidence),
        model_system_version=str(raw["model_system_version"]),
        model_hash=str(raw["model_hash"]),
        policy_hash=str(raw["policy_hash"]),
        feature_schema_version=str(raw["feature_schema_version"]),
        class_scores={str(k): float(v) for k, v in class_scores.items()},
        maximum_score=maximum_score,
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


def _extract_fault_class(transition_type: str, from_state: str, to_state: str) -> str:
    state = from_state if transition_type == "cleared" else to_state
    if not state.startswith(_CONFIRMED_PREFIX):
        raise MalformedStateError(transition_type, from_state, to_state)
    fault_class = state[len(_CONFIRMED_PREFIX) :]
    if not fault_class:
        raise MalformedStateError(transition_type, from_state, to_state)
    return fault_class

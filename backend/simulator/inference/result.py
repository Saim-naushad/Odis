"""Typed per-timestamp inference result (PR176 spec section 7).

One dataclass with a `status` discriminant (mirrors this codebase's own
`robustness.promotion.PromotionDecision` "status/decision + varying
payload" convention) rather than three separate result classes — a future
Kafka consumer pattern-matches on `status` and reads only the fields that
status defines; every other field is `None`/empty by construction
(enforced in `__post_init__`), never a stale value from a previous call.

**Confidence semantics (spec section 9)**: `class_probabilities` /
`maximum_probability` are the promoted logistic-regression pipeline's
native, uncalibrated `predict_proba` output — normalized scores useful
for ranking classes and for the selected alert threshold, **not**
validated real-world likelihoods. No calibration (PR169) is applied or
implied here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class InferenceStatus(StrEnum):
    WARMING_UP = "warming_up"
    VALID_PREDICTION = "valid_prediction"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class EvidenceItem:
    label: str
    value: float
    detail: str

    def to_json_dict(self) -> dict[str, Any]:
        return {"label": self.label, "value": self.value, "detail": self.detail}


@dataclass(frozen=True)
class InferenceResult:
    status: InferenceStatus
    asset_id: str
    timestamp: datetime

    # --- valid_prediction only ---------------------------------------------
    diagnosed_class: str | None = None
    class_probabilities: dict[str, float] | None = None
    maximum_probability: float | None = None
    alert_state: str | None = None
    alert_event: dict[str, Any] | None = None
    evidence: tuple[EvidenceItem, ...] = ()
    model_system_version: str | None = None
    model_hash: str | None = None
    policy_hash: str | None = None
    feature_schema_version: str | None = None

    # --- insufficient_data only ---------------------------------------------
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    invalid_feature_names: tuple[str, ...] = field(default_factory=tuple)

    # --- warming_up only ---------------------------------------------------
    samples_available: int | None = None
    samples_required: int | None = None

    def __post_init__(self) -> None:
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")

        if self.status is InferenceStatus.VALID_PREDICTION:
            if self.diagnosed_class is None or self.class_probabilities is None:
                raise ValueError(
                    "valid_prediction result requires diagnosed_class and "
                    "class_probabilities"
                )
        else:
            if self.diagnosed_class is not None:
                raise ValueError(
                    "diagnosed_class must be None unless status is valid_prediction "
                    "— insufficient data is never reported as a diagnosis"
                )

        if self.status is InferenceStatus.WARMING_UP and (
            self.samples_available is None or self.samples_required is None
        ):
            raise ValueError(
                "warming_up result requires samples_available and samples_required"
            )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "asset_id": self.asset_id,
            "timestamp": self.timestamp.isoformat(),
            "diagnosed_class": self.diagnosed_class,
            "class_probabilities": self.class_probabilities,
            "maximum_probability": self.maximum_probability,
            "alert_state": self.alert_state,
            "alert_event": self.alert_event,
            "evidence": [item.to_json_dict() for item in self.evidence],
            "model_system_version": self.model_system_version,
            "model_hash": self.model_hash,
            "policy_hash": self.policy_hash,
            "feature_schema_version": self.feature_schema_version,
            "reason_codes": list(self.reason_codes),
            "invalid_feature_names": list(self.invalid_feature_names),
            "samples_available": self.samples_available,
            "samples_required": self.samples_required,
        }

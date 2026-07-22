"""AI fault-alert evidence and reasoning-bridge lifecycle domain model.

A confirmed ML fault alert (PR177's `fault_alert_transition.v1`) is
evidence, never authority — this module models exactly that: an
immutable `AiFaultEvidence` record capturing what the model reported and
what deterministic corroboration concluded from it, never an `Action` or
final recommendation the model itself dictated. See
`docs/reasoning-bridge.md`'s "Authority boundary" section.

`AiFaultEvidence.id` is the source alert-transition event's own
deterministic `event_id` (PR177's `identity.deterministic_event_id`) —
this is also this bridge's idempotency mechanism (spec section 4):
attempting to persist a second row with the same id is rejected by the
repository exactly like `SqlAlchemyObservationRepository.save()` already
rejects a duplicate observation id, so replaying the same alert-transition
event can never create a duplicate investigation, corroboration result,
or recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

AlertTransitionType = Literal["confirmed", "class_changed", "cleared"]

CorroborationResult = Literal[
    "corroborated",
    "partially_corroborated",
    "not_corroborated",
    "insufficient_evidence",
    "not_applicable",
]
"""`not_applicable` is used only for `cleared` transitions — clearing
does not diagnose anything, so the four-way corroboration verdict (spec
section 8) does not apply; corroboration/recommendation are simply
skipped and the investigation is marked `CLEARED`."""

InvestigationStatus = Literal["OPEN", "CLEARED"]

FaultRecommendationStatus = Literal["produced", "withheld"]

FaultRecommendationCategory = Literal["investigate", "monitor"]

FaultUrgency = Literal[
    "INFORMATIONAL",
    "INSPECTION_REQUIRED",
    "ELEVATED",
    "URGENT",
]

_ALERT_TRANSITION_TYPES: tuple[AlertTransitionType, ...] = (
    "confirmed",
    "class_changed",
    "cleared",
)
_CORROBORATION_RESULTS: tuple[CorroborationResult, ...] = (
    "corroborated",
    "partially_corroborated",
    "not_corroborated",
    "insufficient_evidence",
    "not_applicable",
)
_INVESTIGATION_STATUSES: tuple[InvestigationStatus, ...] = ("OPEN", "CLEARED")
_RECOMMENDATION_STATUSES: tuple[FaultRecommendationStatus, ...] = (
    "produced",
    "withheld",
)
_RECOMMENDATION_CATEGORIES: tuple[FaultRecommendationCategory, ...] = (
    "investigate",
    "monitor",
)
_URGENCIES: tuple[FaultUrgency, ...] = (
    "INFORMATIONAL",
    "INSPECTION_REQUIRED",
    "ELEVATED",
    "URGENT",
)


@dataclass(frozen=True, slots=True)
class FaultRecommendation:
    """Deterministic, bounded operator guidance derived from corroboration.

    Never constructed from a model score alone, and never present when
    `status == "withheld"` implies an actionable step — a withheld
    recommendation still carries an `action_summary` explaining *why*
    nothing actionable is being recommended (spec section 8: "do not
    silently discard disagreement cases").
    """

    id: str
    status: FaultRecommendationStatus
    category: FaultRecommendationCategory
    urgency: FaultUrgency
    action_summary: str
    reason: str
    supporting_rule_ids: tuple[str, ...]
    supporting_observation_ids: tuple[str, ...]
    recommended_steps: tuple[str, ...]
    limitations: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if self.status not in _RECOMMENDATION_STATUSES:
            raise ValueError(
                "status must be one of: " + ", ".join(_RECOMMENDATION_STATUSES)
            )
        if self.category not in _RECOMMENDATION_CATEGORIES:
            raise ValueError(
                "category must be one of: " + ", ".join(_RECOMMENDATION_CATEGORIES)
            )
        if self.urgency not in _URGENCIES:
            raise ValueError("urgency must be one of: " + ", ".join(_URGENCIES))
        if not self.action_summary:
            raise ValueError("action_summary must not be empty")
        if not self.reason:
            raise ValueError("reason must not be empty")
        if not self.limitations:
            raise ValueError("limitations must not be empty")

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "category": self.category,
            "urgency": self.urgency,
            "action_summary": self.action_summary,
            "reason": self.reason,
            "supporting_rule_ids": list(self.supporting_rule_ids),
            "supporting_observation_ids": list(self.supporting_observation_ids),
            "recommended_steps": list(self.recommended_steps),
            "limitations": self.limitations,
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> FaultRecommendation:
        return cls(
            id=str(data["id"]),
            status=data["status"],
            category=data["category"],
            urgency=data["urgency"],
            action_summary=str(data["action_summary"]),
            reason=str(data["reason"]),
            supporting_rule_ids=tuple(data.get("supporting_rule_ids", ())),
            supporting_observation_ids=tuple(
                data.get("supporting_observation_ids", ())
            ),
            recommended_steps=tuple(data.get("recommended_steps", ())),
            limitations=str(data["limitations"]),
        )


@dataclass(frozen=True, slots=True)
class AiFaultEvidence:
    """One processed AI fault-alert transition, deterministically
    corroborated and (when warranted) recommended against.

    `id` is the *source* alert-transition event's own deterministic
    `event_id` — never independently generated — so persisting this row
    is simultaneously "recording the evidence" and "the idempotency
    check" for this bridge (spec section 4).

    `class_scores`/`maximum_score` are the promoted model's native,
    uncalibrated diagnostic scores (spec section 9) — never referred to
    as "confidence" or a probability anywhere this type is displayed or
    logged; see `docs/reasoning-bridge.md`'s "Score-language caveat".

    `investigation_id` is stable across an AI-detected fault occurrence's
    entire lifecycle (first confirmed alert through class changes to
    clearing); a new alert after a clear starts a *new* `investigation_id`
    (spec section 10) — never reopens the cleared one.
    """

    id: str
    source_event_id: str
    asset_id: str
    observed_at: datetime
    alert_transition_type: AlertTransitionType
    diagnosed_fault_class: str
    from_state: str
    to_state: str
    model_system_version: str
    model_hash: str
    policy_hash: str
    feature_schema_version: str
    class_scores: dict[str, float]
    maximum_score: float
    evidence_items: tuple[dict[str, Any], ...]
    investigation_id: str
    investigation_status: InvestigationStatus
    previous_diagnosed_fault_class: str | None
    corroboration_result: CorroborationResult
    corroboration_rule_ids: tuple[str, ...]
    corroboration_notes: str
    recommendation: FaultRecommendation | None
    recorded_at: datetime

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.source_event_id:
            raise ValueError("source_event_id must not be empty")
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if self.alert_transition_type not in _ALERT_TRANSITION_TYPES:
            raise ValueError(
                "alert_transition_type must be one of: "
                + ", ".join(_ALERT_TRANSITION_TYPES)
            )
        if not self.diagnosed_fault_class:
            raise ValueError("diagnosed_fault_class must not be empty")
        if not self.model_system_version:
            raise ValueError("model_system_version must not be empty")
        if not self.model_hash:
            raise ValueError("model_hash must not be empty")
        if not self.policy_hash:
            raise ValueError("policy_hash must not be empty")
        if not self.feature_schema_version:
            raise ValueError("feature_schema_version must not be empty")
        if not 0.0 <= self.maximum_score <= 1.0:
            raise ValueError("maximum_score must be between 0.0 and 1.0")
        if not self.investigation_id:
            raise ValueError("investigation_id must not be empty")
        if self.investigation_status not in _INVESTIGATION_STATUSES:
            raise ValueError(
                "investigation_status must be one of: "
                + ", ".join(_INVESTIGATION_STATUSES)
            )
        if self.corroboration_result not in _CORROBORATION_RESULTS:
            raise ValueError(
                "corroboration_result must be one of: "
                + ", ".join(_CORROBORATION_RESULTS)
            )

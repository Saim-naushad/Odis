"""Versioned output event: `fault_reasoning_result.v1` (spec section 14).

Published for every processed alert-transition event (confirmed,
class_changed, and cleared alike) — never internal hidden state, never
raw model features. Deterministic event identity so replay is safe: the
same source alert event always produces the same reasoning-result
event_id, mirroring PR177's own `identity.deterministic_event_id`
convention (a documented, deliberate departure from this codebase's
`uuid4()` convention — see PR177's `docs/kafka-fault-inference-worker.md`
for the original rationale, which applies identically here).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from backend.app.domain.ai_fault_evidence import AiFaultEvidence

OUTPUT_EVENT_TYPE = "fault_reasoning_result.v1"
OUTPUT_EVENT_VERSION = "v1"

# Version of *this bridge's own* deterministic corroboration/recommendation
# rule set (`corroboration.py`/`recommendation_policy.py`) — bump when
# those rules change, independent of the model/policy versions the AI
# evidence itself carries.
REASONING_RULE_VERSION = "1.0"

_NAMESPACE = uuid5(NAMESPACE_URL, "https://odis.internal/reasoning-bridge")


def _deterministic_event_id(*parts: str) -> str:
    return str(uuid5(_NAMESPACE, "|".join(parts)))


@dataclass(frozen=True)
class FaultReasoningResultEventV1:
    event_id: str
    event_version: str
    occurred_at: datetime
    source_alert_event_id: str
    asset_id: str
    diagnosed_class: str
    corroboration_result: str
    investigation_id: str
    operational_situation_id: str | None
    recommendation_status: str | None
    recommendation_action_summary: str | None
    urgency: str | None
    supporting_rule_ids: tuple[str, ...]
    supporting_observation_ids: tuple[str, ...]
    model_system_version: str
    model_hash: str
    reasoning_rule_version: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat(),
            "source_alert_event_id": self.source_alert_event_id,
            "asset_id": self.asset_id,
            "diagnosed_class": self.diagnosed_class,
            "corroboration_result": self.corroboration_result,
            "investigation_id": self.investigation_id,
            # This bridge deliberately never invokes the 7-stage
            # ReasoningSession pipeline (see this package's __init__.py
            # docstring), so it never produces an OperationalSituation —
            # always null here, not a stand-in id.
            "operational_situation_id": self.operational_situation_id,
            "recommendation_status": self.recommendation_status,
            "recommendation_action_summary": self.recommendation_action_summary,
            "urgency": self.urgency,
            "supporting_rule_ids": list(self.supporting_rule_ids),
            "supporting_observation_ids": list(self.supporting_observation_ids),
            "model_system_version": self.model_system_version,
            "model_hash": self.model_hash,
            "reasoning_rule_version": self.reasoning_rule_version,
        }


def build_reasoning_result_event(
    evidence: AiFaultEvidence, *, now: datetime | None = None
) -> FaultReasoningResultEventV1:
    occurred_at = now or datetime.now(UTC)
    event_id = _deterministic_event_id(
        OUTPUT_EVENT_TYPE,
        evidence.source_event_id,
        evidence.investigation_id,
    )
    recommendation = evidence.recommendation
    return FaultReasoningResultEventV1(
        event_id=event_id,
        event_version=OUTPUT_EVENT_VERSION,
        occurred_at=occurred_at,
        source_alert_event_id=evidence.source_event_id,
        asset_id=evidence.asset_id,
        diagnosed_class=evidence.diagnosed_fault_class,
        corroboration_result=evidence.corroboration_result,
        investigation_id=evidence.investigation_id,
        operational_situation_id=None,
        recommendation_status=(
            recommendation.status if recommendation is not None else None
        ),
        recommendation_action_summary=(
            recommendation.action_summary if recommendation is not None else None
        ),
        urgency=recommendation.urgency if recommendation is not None else None,
        supporting_rule_ids=(
            recommendation.supporting_rule_ids if recommendation is not None else ()
        ),
        supporting_observation_ids=(
            recommendation.supporting_observation_ids
            if recommendation is not None
            else ()
        ),
        model_system_version=evidence.model_system_version,
        model_hash=evidence.model_hash,
        reasoning_rule_version=REASONING_RULE_VERSION,
    )

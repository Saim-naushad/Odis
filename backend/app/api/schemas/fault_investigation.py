"""AI fault investigation API response schemas.

Operator-safe read model over `AiFaultEvidence`/`FaultRecommendation`
(`backend.app.domain.ai_fault_evidence`). Deliberately excludes
`class_scores` (full per-class model output) and `evidence_items` (raw
upstream model-internal residual/probability payloads) from every
response — these stay persisted for internal diagnostics only and are
never surfaced to an operator. See `docs/fault-investigation-dashboard.md`
for the tiering rationale.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain.ai_fault_evidence import AiFaultEvidence, FaultRecommendation
from domain.entities.observation import Observation

SCORE_CAVEAT_TEXT = (
    "This is an uncalibrated diagnostic ranking score, not a probability or "
    "confidence level — it does not represent the percentage likelihood that "
    "the fault is real."
)

AUTHORITY_BOUNDARY_NOTE = (
    "This fault was detected by a diagnostic model and is evidence, not a "
    "confirmed diagnosis. The recommendation below reflects only what "
    "deterministic telemetry rules corroborated against real observations — "
    "not the model's own score."
)

ObservationEvidenceRole = Literal["supporting", "conflicting", "contextual"]


class ObservationEvidenceSummaryResponse(BaseModel):
    """Compact, bounded observation summary backing a corroboration verdict.

    Every observation returned today is ``"supporting"`` — the reasoning
    bridge's corroboration policy only ever cites the observations that
    support its verdict (see `recommendation_policy.py`); the ``role``
    field exists so a future corroboration policy that also surfaces
    conflicting/contextual readings does not require an API change.
    """

    observation_id: str
    measurement_type: str
    value: float
    unit: str
    observed_at: datetime
    role: ObservationEvidenceRole

    @classmethod
    def from_domain(
        cls, observation: Observation, *, role: ObservationEvidenceRole = "supporting"
    ) -> Self:
        return cls(
            observation_id=observation.id,
            measurement_type=observation.measurement_type.name,
            value=observation.value,
            unit=observation.unit,
            observed_at=observation.timestamp,
            role=role,
        )


class FaultInvestigationProvenanceResponse(BaseModel):
    """Collapsed, secondary-tier provenance metadata.

    Only hashes/versions/score/ids — never raw upstream evidence payloads
    or the full per-class score distribution.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_system_version": "plant_alpha_fault_v1",
                "model_hash": "sha256:abc123...",
                "policy_hash": "sha256:def456...",
                "feature_schema_version": "1.0",
                "latest_model_score": 0.87,
                "score_semantics": SCORE_CAVEAT_TEXT,
                "source_event_id": "evt-001",
                "recorded_at": "2026-07-22T10:00:00Z",
            }
        }
    )

    model_system_version: str
    model_hash: str
    policy_hash: str
    feature_schema_version: str
    latest_model_score: float = Field(
        description=(
            "Uncalibrated diagnostic ranking score, 0.0-1.0. Never a probability."
        )
    )
    score_semantics: str
    source_event_id: str
    recorded_at: datetime

    @classmethod
    def from_domain(cls, evidence: AiFaultEvidence) -> Self:
        return cls(
            model_system_version=evidence.model_system_version,
            model_hash=evidence.model_hash,
            policy_hash=evidence.policy_hash,
            feature_schema_version=evidence.feature_schema_version,
            latest_model_score=evidence.maximum_score,
            score_semantics=SCORE_CAVEAT_TEXT,
            source_event_id=evidence.source_event_id,
            recorded_at=evidence.recorded_at,
        )


class FaultRecommendationSummaryResponse(BaseModel):
    id: str
    status: str
    category: str
    urgency: str
    action_summary: str
    reason: str
    recommended_steps: list[str]
    limitations: str

    @classmethod
    def from_domain(cls, recommendation: FaultRecommendation) -> Self:
        return cls(
            id=recommendation.id,
            status=recommendation.status,
            category=recommendation.category,
            urgency=recommendation.urgency,
            action_summary=recommendation.action_summary,
            reason=recommendation.reason,
            recommended_steps=list(recommendation.recommended_steps),
            limitations=recommendation.limitations,
        )


class FaultInvestigationSummaryResponse(BaseModel):
    """Operator information hierarchy, top to bottom:

    fault state -> corroboration -> urgency -> recommendation ->
    authority boundary -> supporting evidence -> provenance (secondary).
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "investigation_id": "inv-001",
                "asset_id": "asset-stack-1",
                "investigation_status": "OPEN",
                "diagnosed_fault_class": "cooling_degradation",
                "previous_diagnosed_fault_class": None,
                "alert_transition_type": "confirmed",
                "observed_at": "2026-07-22T10:00:00Z",
                "corroboration_result": "corroborated",
                "corroboration_notes": (
                    "stack_temperature is increasing while coolant_flow is "
                    "decreasing — cooling capacity is not compensating."
                ),
                "corroboration_rule_ids": [
                    "cooling_degradation.stack_temperature_increasing"
                ],
                "urgency": "ELEVATED",
                "recommendation_status": "produced",
                "recommendation": {
                    "id": "ai-fault-rec-inv-001-evt-001",
                    "status": "produced",
                    "category": "investigate",
                    "urgency": "ELEVATED",
                    "action_summary": "Inspect cooling subsystem",
                    "reason": "Deterministic telemetry corroborated the alert.",
                    "recommended_steps": ["Check coolant pump", "Verify flow sensor"],
                    "limitations": (
                        "Automated inspection cannot substitute for a manual check."
                    ),
                },
                "authority_boundary_note": AUTHORITY_BOUNDARY_NOTE,
                "supporting_evidence": [],
                "provenance": None,
            }
        }
    )

    investigation_id: str
    asset_id: str
    investigation_status: str
    diagnosed_fault_class: str
    previous_diagnosed_fault_class: str | None
    alert_transition_type: str
    observed_at: datetime

    corroboration_result: str
    corroboration_notes: str
    corroboration_rule_ids: list[str]

    urgency: str | None = Field(
        default=None, description="Null for cleared transitions (not_applicable)."
    )
    recommendation_status: str | None = None
    recommendation: FaultRecommendationSummaryResponse | None = None

    authority_boundary_note: str = AUTHORITY_BOUNDARY_NOTE

    supporting_evidence: list[ObservationEvidenceSummaryResponse] = Field(
        default_factory=list
    )
    provenance: FaultInvestigationProvenanceResponse | None = None

    @classmethod
    def from_domain(
        cls,
        evidence: AiFaultEvidence,
        *,
        supporting_observations: list[Observation] | None = None,
        include_provenance: bool = True,
    ) -> Self:
        recommendation = (
            FaultRecommendationSummaryResponse.from_domain(evidence.recommendation)
            if evidence.recommendation is not None
            else None
        )
        return cls(
            investigation_id=evidence.investigation_id,
            asset_id=evidence.asset_id,
            investigation_status=evidence.investigation_status,
            diagnosed_fault_class=evidence.diagnosed_fault_class,
            previous_diagnosed_fault_class=evidence.previous_diagnosed_fault_class,
            alert_transition_type=evidence.alert_transition_type,
            observed_at=evidence.observed_at,
            corroboration_result=evidence.corroboration_result,
            corroboration_notes=evidence.corroboration_notes,
            corroboration_rule_ids=list(evidence.corroboration_rule_ids),
            urgency=(
                evidence.recommendation.urgency
                if evidence.recommendation is not None
                else None
            ),
            recommendation_status=(
                evidence.recommendation.status
                if evidence.recommendation is not None
                else None
            ),
            recommendation=recommendation,
            supporting_evidence=[
                ObservationEvidenceSummaryResponse.from_domain(observation)
                for observation in (supporting_observations or [])
            ],
            provenance=(
                FaultInvestigationProvenanceResponse.from_domain(evidence)
                if include_provenance
                else None
            ),
        )


class ActiveFaultInvestigationResponse(BaseModel):
    """Response envelope for the active-investigation endpoint.

    ``active_investigation`` is ``null`` (HTTP 200) whenever the asset has
    no AI-fault history yet, or its latest investigation has already been
    cleared — this is a normal operational state, never a 404.
    """

    active_investigation: FaultInvestigationSummaryResponse | None


class FaultInvestigationDetailResponse(BaseModel):
    """Full chronological lifecycle of one AI-fault investigation."""

    investigation_id: str
    asset_id: str
    current: FaultInvestigationSummaryResponse
    timeline: list[FaultInvestigationSummaryResponse]

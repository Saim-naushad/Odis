"""Mapping between domain AI fault evidence and its ORM model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from backend.app.domain.ai_fault_evidence import (
    AiFaultEvidence,
    AlertTransitionType,
    CorroborationResult,
    FaultRecommendation,
    InvestigationStatus,
)
from backend.app.infrastructure.database.models.ai_fault_evidence import (
    AiFaultEvidenceModel,
)


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def ai_fault_evidence_to_model(evidence: AiFaultEvidence) -> AiFaultEvidenceModel:
    """Map a domain AI fault evidence record to its SQLAlchemy representation."""
    return AiFaultEvidenceModel(
        id=evidence.id,
        source_event_id=evidence.source_event_id,
        asset_id=evidence.asset_id,
        observed_at=evidence.observed_at,
        alert_transition_type=evidence.alert_transition_type,
        diagnosed_fault_class=evidence.diagnosed_fault_class,
        from_state=evidence.from_state,
        to_state=evidence.to_state,
        model_system_version=evidence.model_system_version,
        model_hash=evidence.model_hash,
        policy_hash=evidence.policy_hash,
        feature_schema_version=evidence.feature_schema_version,
        class_scores=dict(evidence.class_scores),
        maximum_score=evidence.maximum_score,
        evidence_items=list(evidence.evidence_items),
        investigation_id=evidence.investigation_id,
        investigation_status=evidence.investigation_status,
        previous_diagnosed_fault_class=evidence.previous_diagnosed_fault_class,
        corroboration_result=evidence.corroboration_result,
        corroboration_rule_ids=list(evidence.corroboration_rule_ids),
        corroboration_notes=evidence.corroboration_notes,
        recommendation=(
            evidence.recommendation.to_json_dict()
            if evidence.recommendation is not None
            else None
        ),
        recorded_at=evidence.recorded_at,
    )


def ai_fault_evidence_to_domain(model: AiFaultEvidenceModel) -> AiFaultEvidence:
    """Map a SQLAlchemy AI fault evidence row to the domain entity."""
    recommendation_payload = model.recommendation
    return AiFaultEvidence(
        id=model.id,
        source_event_id=model.source_event_id,
        asset_id=model.asset_id,
        observed_at=_ensure_utc(model.observed_at),
        alert_transition_type=cast(AlertTransitionType, model.alert_transition_type),
        diagnosed_fault_class=model.diagnosed_fault_class,
        from_state=model.from_state,
        to_state=model.to_state,
        model_system_version=model.model_system_version,
        model_hash=model.model_hash,
        policy_hash=model.policy_hash,
        feature_schema_version=model.feature_schema_version,
        class_scores=dict(model.class_scores),
        maximum_score=model.maximum_score,
        evidence_items=tuple(model.evidence_items),
        investigation_id=model.investigation_id,
        investigation_status=cast(InvestigationStatus, model.investigation_status),
        previous_diagnosed_fault_class=model.previous_diagnosed_fault_class,
        corroboration_result=cast(CorroborationResult, model.corroboration_result),
        corroboration_rule_ids=tuple(model.corroboration_rule_ids),
        corroboration_notes=model.corroboration_notes,
        recommendation=(
            FaultRecommendation.from_json_dict(recommendation_payload)
            if recommendation_payload is not None
            else None
        ),
        recorded_at=_ensure_utc(model.recorded_at),
    )

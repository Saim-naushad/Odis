"""SQLAlchemy ORM model for persisted AI fault-alert evidence."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.infrastructure.database.base import Base


class AiFaultEvidenceModel(Base):
    """Infrastructure representation of a domain `AiFaultEvidence` row.

    One row per processed alert-transition event, one small table
    covering evidence + corroboration + recommendation + investigation
    linkage (spec section 16: "avoid a large ML-specific schema; reuse
    generic structures where possible") — never all 153 model features,
    only the small curated `evidence_items` PR176/177 already compute.

    `id` (the primary key) is the source event's own deterministic
    `event_id`, which is this bridge's entire idempotency mechanism: a
    duplicate insert is rejected at the repository layer exactly like
    `ObservationModel`'s own id-uniqueness check.
    """

    __tablename__ = "ai_fault_evidence"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_event_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    alert_transition_type: Mapped[str] = mapped_column(String, nullable=False)
    diagnosed_fault_class: Mapped[str] = mapped_column(String, nullable=False)
    from_state: Mapped[str] = mapped_column(String, nullable=False)
    to_state: Mapped[str] = mapped_column(String, nullable=False)
    model_system_version: Mapped[str] = mapped_column(String, nullable=False)
    model_hash: Mapped[str] = mapped_column(String, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String, nullable=False)
    feature_schema_version: Mapped[str] = mapped_column(String, nullable=False)
    class_scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    maximum_score: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_items: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    investigation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    investigation_status: Mapped[str] = mapped_column(String, nullable=False)
    previous_diagnosed_fault_class: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    corroboration_result: Mapped[str] = mapped_column(String, nullable=False)
    corroboration_rule_ids: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    corroboration_notes: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

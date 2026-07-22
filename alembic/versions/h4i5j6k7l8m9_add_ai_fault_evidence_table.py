"""add ai fault evidence table

Revision ID: h4i5j6k7l8m9
Revises: c7d8e9f0a1b2
Create Date: 2026-07-21 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "h4i5j6k7l8m9"
down_revision: str | Sequence[str] | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ai_fault_evidence",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source_event_id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alert_transition_type", sa.String(), nullable=False),
        sa.Column("diagnosed_fault_class", sa.String(), nullable=False),
        sa.Column("from_state", sa.String(), nullable=False),
        sa.Column("to_state", sa.String(), nullable=False),
        sa.Column("model_system_version", sa.String(), nullable=False),
        sa.Column("model_hash", sa.String(), nullable=False),
        sa.Column("policy_hash", sa.String(), nullable=False),
        sa.Column("feature_schema_version", sa.String(), nullable=False),
        sa.Column("class_scores", sa.JSON(), nullable=False),
        sa.Column("maximum_score", sa.Float(), nullable=False),
        sa.Column("evidence_items", sa.JSON(), nullable=False),
        sa.Column("investigation_id", sa.String(), nullable=False),
        sa.Column("investigation_status", sa.String(), nullable=False),
        sa.Column("previous_diagnosed_fault_class", sa.String(), nullable=True),
        sa.Column("corroboration_result", sa.String(), nullable=False),
        sa.Column("corroboration_rule_ids", sa.JSON(), nullable=False),
        sa.Column("corroboration_notes", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.JSON(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ai_fault_evidence_source_event_id"),
        "ai_fault_evidence",
        ["source_event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_fault_evidence_asset_id"),
        "ai_fault_evidence",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_ai_fault_evidence_investigation_id"),
        "ai_fault_evidence",
        ["investigation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_ai_fault_evidence_investigation_id"),
        table_name="ai_fault_evidence",
    )
    op.drop_index(
        op.f("ix_ai_fault_evidence_asset_id"),
        table_name="ai_fault_evidence",
    )
    op.drop_index(
        op.f("ix_ai_fault_evidence_source_event_id"),
        table_name="ai_fault_evidence",
    )
    op.drop_table("ai_fault_evidence")

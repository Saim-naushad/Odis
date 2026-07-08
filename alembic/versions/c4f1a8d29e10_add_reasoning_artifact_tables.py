"""add reasoning artifact tables

Revision ID: c4f1a8d29e10
Revises: b8265a976460
Create Date: 2026-07-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4f1a8d29e10"
down_revision: str | Sequence[str] | None = "b8265a976460"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "reasoning_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "operational_situations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("goal_id", sa.String(), nullable=False),
        sa.Column("observation_ids", sa.JSON(), nullable=False),
        sa.Column("assessment", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "decision_contexts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("goal_id", sa.String(), nullable=False),
        sa.Column("situation_id", sa.String(), nullable=False),
        sa.Column("assessment", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "decision_plans",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("context_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("priority", sa.String(), nullable=False),
        sa.Column("recommendation", sa.String(), nullable=False),
        sa.Column("justification", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reasoning_run_indexes",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("observation_ids", sa.JSON(), nullable=False),
        sa.Column("situation_id", sa.String(), nullable=False),
        sa.Column("context_id", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column("action_id", sa.String(), nullable=False),
        sa.Column("outcome_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "structured_assessments",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("trend_direction", sa.String(), nullable=False),
        sa.Column("variation_level", sa.String(), nullable=False),
        sa.Column("has_correlations", sa.Boolean(), nullable=False),
        sa.Column("has_contradictions", sa.Boolean(), nullable=False),
        sa.Column("has_unexpected_expectations", sa.Boolean(), nullable=False),
        sa.Column("has_indeterminate_expectations", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["reasoning_runs.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_table(
        "reasoning_traces",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["reasoning_runs.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("reasoning_traces")
    op.drop_table("structured_assessments")
    op.drop_table("reasoning_run_indexes")
    op.drop_table("decision_plans")
    op.drop_table("decision_contexts")
    op.drop_table("operational_situations")
    op.drop_table("reasoning_runs")

"""add reasoning jobs table

Revision ID: e8f3c2d51a30
Revises: d7e2b1c40f20
Create Date: 2026-07-09 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8f3c2d51a30"
down_revision: str | Sequence[str] | None = "d7e2b1c40f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "reasoning_jobs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reasoning_jobs_asset_id"),
        "reasoning_jobs",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reasoning_jobs_status"),
        "reasoning_jobs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_reasoning_jobs_status"), table_name="reasoning_jobs")
    op.drop_index(op.f("ix_reasoning_jobs_asset_id"), table_name="reasoning_jobs")
    op.drop_table("reasoning_jobs")

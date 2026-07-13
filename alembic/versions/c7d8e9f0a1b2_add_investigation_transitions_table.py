"""add investigation transitions table

Revision ID: c7d8e9f0a1b2
Revises: 811e4ab34c7c
Create Date: 2026-07-13 21:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | Sequence[str] | None = "811e4ab34c7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "investigation_transitions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("recommendation_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("actor_display_name", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_investigation_transitions_asset_id"),
        "investigation_transitions",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_investigation_transitions_recommendation_id"),
        "investigation_transitions",
        ["recommendation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_investigation_transitions_recommendation_id"),
        table_name="investigation_transitions",
    )
    op.drop_index(
        op.f("ix_investigation_transitions_asset_id"),
        table_name="investigation_transitions",
    )
    op.drop_table("investigation_transitions")

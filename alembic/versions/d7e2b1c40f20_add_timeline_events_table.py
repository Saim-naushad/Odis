"""add timeline events table

Revision ID: d7e2b1c40f20
Revises: c4f1a8d29e10
Create Date: 2026-07-09 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7e2b1c40f20"
down_revision: str | Sequence[str] | None = "c4f1a8d29e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "timeline_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_timeline_events_asset_id"),
        "timeline_events",
        ["asset_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_timeline_events_asset_id"), table_name="timeline_events")
    op.drop_table("timeline_events")

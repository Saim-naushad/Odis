"""add worker heartbeats table

Revision ID: f1a2b3c4d5e6
Revises: e8f3c2d51a30
Create Date: 2026-07-10 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "e8f3c2d51a30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    op.create_index(
        op.f("ix_worker_heartbeats_last_seen_at"),
        "worker_heartbeats",
        ["last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_worker_heartbeats_last_seen_at"),
        table_name="worker_heartbeats",
    )
    op.drop_table("worker_heartbeats")

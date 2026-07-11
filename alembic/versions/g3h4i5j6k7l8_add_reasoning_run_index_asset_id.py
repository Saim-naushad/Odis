"""add asset_id index to reasoning_run_indexes

Revision ID: g3h4i5j6k7l8
Revises: a9c4e1f72b03
Create Date: 2026-07-11 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "g3h4i5j6k7l8"
down_revision: str | Sequence[str] | None = "a9c4e1f72b03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add asset_id for bounded per-asset monitoring reads."""
    op.add_column(
        "reasoning_run_indexes",
        sa.Column("asset_id", sa.String(), nullable=True),
    )
    op.execute(
        """
        UPDATE reasoning_run_indexes AS rri
        SET asset_id = (
            SELECT o.asset_id
            FROM observations o
            WHERE o.id = (rri.observation_ids::json)->>0
            LIMIT 1
        )
        """
    )
    op.alter_column("reasoning_run_indexes", "asset_id", nullable=False)
    op.create_index(
        "ix_reasoning_run_indexes_asset_id",
        "reasoning_run_indexes",
        ["asset_id"],
    )


def downgrade() -> None:
    """Remove asset_id lookup support."""
    op.drop_index(
        "ix_reasoning_run_indexes_asset_id",
        table_name="reasoning_run_indexes",
    )
    op.drop_column("reasoning_run_indexes", "asset_id")

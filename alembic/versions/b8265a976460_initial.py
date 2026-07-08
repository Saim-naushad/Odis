"""initial

Revision ID: b8265a976460
Revises:
Create Date: 2026-07-08 10:38:18.597584

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8265a976460"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "observations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measurement_type_name", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_observations_asset_id"),
        "observations",
        ["asset_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_observations_asset_id"), table_name="observations")
    op.drop_table("observations")

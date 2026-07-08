"""initial

Revision ID: b8265a976460
Revises:
Create Date: 2026-07-08 10:38:18.597584

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "b8265a976460"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

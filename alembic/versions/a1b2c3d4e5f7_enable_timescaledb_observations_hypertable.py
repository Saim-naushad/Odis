"""enable timescaledb observations hypertable

Revision ID: a1b2c3d4e5f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-10 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_observations_hypertable(connection: sa.Connection) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM timescaledb_information.hypertables
            WHERE hypertable_schema = current_schema()
              AND hypertable_name = 'observations'
            """
        )
    )
    return result.scalar() is not None


def upgrade() -> None:
    """Enable TimescaleDB and convert observations to a hypertable."""
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    connection = op.get_bind()
    if not _is_observations_hypertable(connection):
        op.drop_constraint("observations_pkey", "observations", type_="primary")
        op.execute(
            """
            SELECT create_hypertable(
                'observations',
                'timestamp',
                if_not_exists => TRUE,
                migrate_data => TRUE,
                chunk_time_interval => INTERVAL '1 day'
            )
            """
        )

    op.execute("CREATE INDEX IF NOT EXISTS ix_observations_id ON observations (id)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_observations_asset_id_timestamp
        ON observations (asset_id, timestamp DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_observations_asset_measurement_timestamp
        ON observations (asset_id, measurement_type_name, timestamp DESC)
        """
    )


def downgrade() -> None:
    """Remove TimescaleDB-specific observation indexes.

    Hypertable conversion is intentionally not reversed because TimescaleDB
    does not provide a safe in-place demotion path for existing data.
    """
    op.execute("DROP INDEX IF EXISTS ix_observations_asset_measurement_timestamp")
    op.execute("DROP INDEX IF EXISTS ix_observations_asset_id_timestamp")
    op.execute("DROP INDEX IF EXISTS ix_observations_id")

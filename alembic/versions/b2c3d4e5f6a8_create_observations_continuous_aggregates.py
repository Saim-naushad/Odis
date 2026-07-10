"""create observations continuous aggregates

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-07-10 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a8"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HOURLY_VIEW = "observations_hourly"
_DAILY_VIEW = "observations_daily"


def _continuous_aggregate_exists(connection: sa.Connection, view_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM timescaledb_information.continuous_aggregates
            WHERE view_schema = current_schema()
              AND view_name = :view_name
            """
        ),
        {"view_name": view_name},
    )
    return result.scalar() is not None


def _refresh_policy_exists(connection: sa.Connection, view_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM timescaledb_information.jobs
            WHERE proc_name = 'policy_refresh_continuous_aggregate'
              AND hypertable_schema = current_schema()
              AND hypertable_name = :view_name
            """
        ),
        {"view_name": view_name},
    )
    return result.scalar() is not None


def _create_hourly_aggregate(connection: sa.Connection) -> None:
    if _continuous_aggregate_exists(connection, _HOURLY_VIEW):
        return

    op.execute(
        f"""
        CREATE MATERIALIZED VIEW {_HOURLY_VIEW}
        WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
        SELECT
            time_bucket('1 hour', "timestamp") AS bucket,
            asset_id,
            measurement_type_name,
            avg(value) AS avg_value,
            min(value) AS min_value,
            max(value) AS max_value,
            count(*) AS sample_count,
            last(unit, "timestamp") AS unit
        FROM observations
        GROUP BY bucket, asset_id, measurement_type_name
        WITH NO DATA
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_{_HOURLY_VIEW}_asset_measurement_bucket
        ON {_HOURLY_VIEW} (asset_id, measurement_type_name, bucket DESC)
        """
    )


def _create_daily_aggregate(connection: sa.Connection) -> None:
    if _continuous_aggregate_exists(connection, _DAILY_VIEW):
        return

    op.execute(
        f"""
        CREATE MATERIALIZED VIEW {_DAILY_VIEW}
        WITH (timescaledb.continuous, timescaledb.materialized_only = false) AS
        SELECT
            time_bucket('1 day', "timestamp") AS bucket,
            asset_id,
            measurement_type_name,
            avg(value) AS avg_value,
            min(value) AS min_value,
            max(value) AS max_value,
            count(*) AS sample_count,
            last(unit, "timestamp") AS unit
        FROM observations
        GROUP BY bucket, asset_id, measurement_type_name
        WITH NO DATA
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_{_DAILY_VIEW}_asset_measurement_bucket
        ON {_DAILY_VIEW} (asset_id, measurement_type_name, bucket DESC)
        """
    )


def _add_hourly_refresh_policy(connection: sa.Connection) -> None:
    if _refresh_policy_exists(connection, _HOURLY_VIEW):
        return

    op.execute(
        f"""
        SELECT add_continuous_aggregate_policy(
            '{_HOURLY_VIEW}',
            start_offset => INTERVAL '7 days',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour'
        )
        """
    )


def _add_daily_refresh_policy(connection: sa.Connection) -> None:
    if _refresh_policy_exists(connection, _DAILY_VIEW):
        return

    op.execute(
        f"""
        SELECT add_continuous_aggregate_policy(
            '{_DAILY_VIEW}',
            start_offset => INTERVAL '90 days',
            end_offset => INTERVAL '1 day',
            schedule_interval => INTERVAL '1 day'
        )
        """
    )


def upgrade() -> None:
    """Create hourly/daily continuous aggregates and refresh policies."""
    connection = op.get_bind()
    _create_hourly_aggregate(connection)
    _create_daily_aggregate(connection)
    _add_hourly_refresh_policy(connection)
    _add_daily_refresh_policy(connection)


def downgrade() -> None:
    """Remove continuous aggregate refresh policies and views."""
    connection = op.get_bind()

    for view_name in (_DAILY_VIEW, _HOURLY_VIEW):
        if _refresh_policy_exists(connection, view_name):
            op.execute(
                sa.text(
                    """
                    SELECT remove_continuous_aggregate_policy(
                        :view_name, if_exists => TRUE
                    )
                    """
                ),
                {"view_name": view_name},
            )

    op.execute(f"DROP INDEX IF EXISTS ix_{_DAILY_VIEW}_asset_measurement_bucket")
    op.execute(f"DROP INDEX IF EXISTS ix_{_HOURLY_VIEW}_asset_measurement_bucket")
    op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {_DAILY_VIEW} CASCADE")
    op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {_HOURLY_VIEW} CASCADE")

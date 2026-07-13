"""add reasoning job dirty and outstanding index

Revision ID: 811e4ab34c7c
Revises: g3h4i5j6k7l8
Create Date: 2026-07-13 17:54:59.328590

Reconciliation note
--------------------
Before this migration, ``reasoning_jobs`` had no constraint preventing more
than one PENDING/RUNNING row per ``asset_id`` (the exact bug this migration
fixes). The upgrade first reconciles any pre-existing duplicates: for each
``asset_id`` with more than one outstanding row, the RUNNING row (if any,
otherwise the oldest PENDING row) survives and every other outstanding row
for that asset is forced to FAILED.

Reconciled rows are marked with a single, fixed, hardcoded
``completed_at`` value equal to this migration's own Create Date above,
``TIMESTAMP WITH TIME ZONE '2026-07-13 17:54:59.328590+00'`` — never
``now()``. A row genuinely failed by the worker will not, except by
adversarial coincidence, share that exact instant, so any row reconciled by
this migration can always be found later with:

    SELECT * FROM reasoning_jobs
    WHERE status = 'FAILED'
      AND completed_at = TIMESTAMP WITH TIME ZONE '2026-07-13 17:54:59.328590+00';

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "811e4ab34c7c"
down_revision: str | Sequence[str] | None = "g3h4i5j6k7l8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RECONCILED_COMPLETED_AT = "2026-07-13 17:54:59.328590+00"
_OUTSTANDING_WHERE = "status IN ('PENDING', 'RUNNING')"


def upgrade() -> None:
    """Reconcile duplicate outstanding jobs, then add dirty/coalesced_count
    and the partial unique index that keeps them from recurring."""
    op.execute(
        f"""
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY asset_id
                    ORDER BY
                        CASE WHEN status = 'RUNNING' THEN 0 ELSE 1 END,
                        created_at ASC
                ) AS rn
            FROM reasoning_jobs
            WHERE {_OUTSTANDING_WHERE}
        )
        UPDATE reasoning_jobs
        SET status = 'FAILED',
            completed_at = TIMESTAMP WITH TIME ZONE '{_RECONCILED_COMPLETED_AT}'
        FROM ranked
        WHERE reasoning_jobs.id = ranked.id
          AND ranked.rn > 1
        """
    )

    op.add_column(
        "reasoning_jobs",
        sa.Column("dirty", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "reasoning_jobs",
        sa.Column(
            "coalesced_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    op.execute(
        f"""
        DO $$
        DECLARE
            violation_count integer;
        BEGIN
            SELECT COUNT(*) INTO violation_count
            FROM (
                SELECT asset_id
                FROM reasoning_jobs
                WHERE {_OUTSTANDING_WHERE}
                GROUP BY asset_id
                HAVING COUNT(*) > 1
            ) AS violations;

            IF violation_count > 0 THEN
                RAISE EXCEPTION
                    'reasoning_jobs still has % asset(s) with multiple '
                    'outstanding jobs after reconciliation', violation_count;
            END IF;
        END $$;
        """
    )
    op.create_index(
        "ux_reasoning_jobs_outstanding",
        "reasoning_jobs",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text(_OUTSTANDING_WHERE),
    )


def downgrade() -> None:
    """Drop the outstanding-job constraint and its supporting columns."""
    op.drop_index("ux_reasoning_jobs_outstanding", table_name="reasoning_jobs")
    op.drop_column("reasoning_jobs", "coalesced_count")
    op.drop_column("reasoning_jobs", "dirty")

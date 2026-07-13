"""SQLAlchemy-backed reasoning job repository."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, insert, select, text
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.app.domain.reasoning_job import ReasoningJob, ReasoningJobStatus
from backend.app.domain.repositories.reasoning_job_repository import (
    ReasoningJobRepository,
)
from backend.app.infrastructure.database.mappers.reasoning_job import (
    reasoning_job_row_to_domain,
    reasoning_job_to_domain,
    reasoning_job_to_model,
)
from backend.app.infrastructure.database.models.reasoning_job import (
    _OUTSTANDING_WHERE,
    ReasoningJobModel,
)
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository

_RETURNING_COLUMNS = (
    ReasoningJobModel.id,
    ReasoningJobModel.asset_id,
    ReasoningJobModel.status,
    ReasoningJobModel.created_at,
    ReasoningJobModel.started_at,
    ReasoningJobModel.completed_at,
    ReasoningJobModel.attempts,
    ReasoningJobModel.dirty,
    ReasoningJobModel.coalesced_count,
)


class SqlAlchemyReasoningJobRepository(SqlAlchemyRepository, ReasoningJobRepository):
    """Persist reasoning jobs in PostgreSQL through SQLAlchemy."""

    def save(self, job: ReasoningJob) -> None:
        self._session.add(reasoning_job_to_model(job))
        self._session.flush()

    def get(self, job_id: str) -> ReasoningJob | None:
        model = self._session.get(ReasoningJobModel, job_id)
        if model is None:
            return None
        return reasoning_job_to_domain(model)

    def claim_oldest_pending(self) -> ReasoningJob | None:
        statement = (
            select(ReasoningJobModel)
            .where(ReasoningJobModel.status == ReasoningJobStatus.PENDING.value)
            .order_by(ReasoningJobModel.created_at)
            .limit(1)
        )
        dialect_name = (
            self._session.bind.dialect.name
            if self._session.bind is not None
            else None
        )
        if dialect_name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        else:
            statement = statement.with_for_update()

        model = self._session.scalars(statement).first()
        if model is None:
            return None

        now = datetime.now(UTC)
        model.status = ReasoningJobStatus.RUNNING.value
        model.started_at = now
        model.attempts = model.attempts + 1
        self._session.flush()
        return reasoning_job_to_domain(model)

    def update(self, job: ReasoningJob) -> None:
        model = self._session.get(ReasoningJobModel, job.id)
        if model is None:
            msg = f"reasoning job with id {job.id!r} not found"
            raise ValueError(msg)
        model.asset_id = job.asset_id
        model.status = job.status.value
        model.created_at = job.created_at
        model.started_at = job.started_at
        model.completed_at = job.completed_at
        model.attempts = job.attempts
        self._session.flush()

    def count_by_status(self, status: str) -> int:
        statement = (
            select(func.count())
            .select_from(ReasoningJobModel)
            .where(ReasoningJobModel.status == status)
        )
        return int(self._session.scalar(statement) or 0)

    def enqueue_or_mark_dirty(self, asset_id: str) -> tuple[ReasoningJob, bool]:
        now = datetime.now(UTC)
        candidate_id = str(uuid4())
        values = {
            "id": candidate_id,
            "asset_id": asset_id,
            "status": ReasoningJobStatus.PENDING.value,
            "created_at": now,
            "started_at": None,
            "completed_at": None,
            "attempts": 0,
            "dirty": False,
            "coalesced_count": 0,
        }
        # PostgreSQL's ON CONFLICT arbiter inference must match this
        # predicate against the partial index's own stored predicate at
        # plan time. A parameterized predicate (e.g. status.in_(...), which
        # binds the comparison values) works for the first few executions on
        # a connection while Postgres still uses a "custom" plan, but fails
        # with "no unique or exclusion constraint matching the ON CONFLICT
        # specification" once the connection switches to a cached "generic"
        # plan (typically after ~5 executions) and can no longer resolve the
        # bound values at plan time. Using the exact literal text the index
        # was created with (see ReasoningJobModel's _OUTSTANDING_WHERE)
        # keeps the predicate a constant expression Postgres can always
        # match, regardless of custom vs. generic planning.
        outstanding = text(_OUTSTANDING_WHERE)
        on_conflict_set = {
            "dirty": True,
            "coalesced_count": ReasoningJobModel.coalesced_count + 1,
        }
        dialect_name = (
            self._session.bind.dialect.name
            if self._session.bind is not None
            else None
        )
        # Dialect-specific INSERT ... ON CONFLICT constructs are not
        # interchangeable at the type level (each returns its own dialect's
        # Insert subtype), so each branch is built out in full rather than
        # sharing a helper that returns "the" insert constructor.
        if dialect_name == "postgresql":
            statement = (
                pg_insert(ReasoningJobModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[ReasoningJobModel.asset_id],
                    index_where=outstanding,
                    set_=on_conflict_set,
                )
                .returning(*_RETURNING_COLUMNS)
            )
        else:
            statement = (
                sqlite_insert(ReasoningJobModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[ReasoningJobModel.asset_id],
                    index_where=outstanding,
                    set_=on_conflict_set,
                )
                .returning(*_RETURNING_COLUMNS)
            )
        row = self._session.execute(statement).one()
        # This statement bypasses the ORM identity map; any already-loaded
        # instance for this row (e.g. from an earlier claim in the same
        # session) would otherwise keep stale pre-upsert attribute values.
        self._session.expire_all()
        job = reasoning_job_row_to_domain(row)
        created = job.id == candidate_id
        return job, created

    def _finish_and_reschedule(
        self, job: ReasoningJob, terminal_status: ReasoningJobStatus
    ) -> tuple[ReasoningJob, ReasoningJob | None]:
        now = datetime.now(UTC)
        # Step 1: move the job to a terminal status FIRST. Only after it no
        # longer matches status IN ('PENDING', 'RUNNING') can a follow-up row
        # be inserted without violating the partial unique index, which
        # otherwise treats the still-outstanding old row and a new PENDING
        # row for the same asset as a conflict within this same transaction.
        finish_statement = (
            sa_update(ReasoningJobModel)
            .where(ReasoningJobModel.id == job.id)
            .values(status=terminal_status.value, completed_at=now)
            .returning(*_RETURNING_COLUMNS)
        )
        finished_row = self._session.execute(finish_statement).one()
        self._session.expire_all()
        finished_job = reasoning_job_row_to_domain(finished_row)

        if not finished_job.dirty:
            return finished_job, None

        # Step 2: clear dirty on the now-terminal row so job history never
        # shows an unconsumed request on a row nothing will act on again.
        self._session.execute(
            sa_update(ReasoningJobModel)
            .where(ReasoningJobModel.id == job.id)
            .values(dirty=False)
        )
        self._session.expire_all()
        finished_job = replace(finished_job, dirty=False)

        # Step 3: only now insert the follow-up job. The old row already left
        # the partial index's predicate in step 1, so this plain insert
        # cannot conflict with it.
        reschedule_statement = (
            insert(ReasoningJobModel)
            .values(
                id=str(uuid4()),
                asset_id=finished_job.asset_id,
                status=ReasoningJobStatus.PENDING.value,
                created_at=now,
                started_at=None,
                completed_at=None,
                attempts=0,
                dirty=False,
                coalesced_count=0,
            )
            .returning(*_RETURNING_COLUMNS)
        )
        rescheduled_row = self._session.execute(reschedule_statement).one()
        self._session.expire_all()
        rescheduled_job = reasoning_job_row_to_domain(rescheduled_row)
        return finished_job, rescheduled_job

    def complete_and_reschedule(
        self, job: ReasoningJob
    ) -> tuple[ReasoningJob, ReasoningJob | None]:
        return self._finish_and_reschedule(job, ReasoningJobStatus.COMPLETED)

    def fail_and_reschedule(
        self, job: ReasoningJob
    ) -> tuple[ReasoningJob, ReasoningJob | None]:
        return self._finish_and_reschedule(job, ReasoningJobStatus.FAILED)

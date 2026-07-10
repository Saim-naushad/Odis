"""SQLAlchemy-backed reasoning job repository."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from backend.app.domain.reasoning_job import ReasoningJob, ReasoningJobStatus
from backend.app.domain.repositories.reasoning_job_repository import (
    ReasoningJobRepository,
)
from backend.app.infrastructure.database.mappers.reasoning_job import (
    reasoning_job_to_domain,
    reasoning_job_to_model,
)
from backend.app.infrastructure.database.models.reasoning_job import ReasoningJobModel
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository


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

"""SQLAlchemy-backed reasoning run repository."""

from sqlalchemy.exc import IntegrityError

from application.reasoning_run import ReasoningRun
from backend.app.infrastructure.database.mappers.reasoning_run import (
    reasoning_run_to_domain,
    reasoning_run_to_model,
)
from backend.app.infrastructure.database.models.reasoning_run import ReasoningRunModel
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository
from domain.repositories.reasoning_run_repository import (
    PersistedReasoningRun,
    ReasoningRunRepository,
)


class SqlAlchemyReasoningRunRepository(SqlAlchemyRepository, ReasoningRunRepository):
    """Persist reasoning runs in PostgreSQL through SQLAlchemy."""

    def get(self, run_id: str) -> ReasoningRun | None:
        model = self._session.get(ReasoningRunModel, run_id)
        if model is None:
            return None
        return reasoning_run_to_domain(model)

    def save(self, run: PersistedReasoningRun) -> None:
        if self._session.get(ReasoningRunModel, run.id) is not None:
            raise ValueError(f"reasoning run with id {run.id!r} already exists")

        model = reasoning_run_to_model(run)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            raise ValueError(
                f"reasoning run with id {run.id!r} already exists"
            ) from None

"""SQLAlchemy-backed reasoning trace repository."""

from sqlalchemy.exc import IntegrityError

from application.reasoning_trace import ReasoningTrace
from application.reasoning_trace_repository import ReasoningTraceRepository
from backend.app.infrastructure.database.mappers.reasoning_trace import (
    reasoning_trace_to_domain,
    reasoning_trace_to_model,
)
from backend.app.infrastructure.database.models.reasoning_trace import (
    ReasoningTraceModel,
)
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository


class SqlAlchemyReasoningTraceRepository(
    SqlAlchemyRepository,
    ReasoningTraceRepository,
):
    """Persist reasoning traces in PostgreSQL through SQLAlchemy."""

    def get_by_run_id(self, run_id: str) -> ReasoningTrace | None:
        model = self._session.get(ReasoningTraceModel, run_id)
        if model is None:
            return None
        return reasoning_trace_to_domain(model)

    def save(self, run_id: str, trace: ReasoningTrace) -> None:
        if self._session.get(ReasoningTraceModel, run_id) is not None:
            raise ValueError(f"reasoning trace for run_id {run_id!r} already exists")

        model = reasoning_trace_to_model(run_id, trace)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            raise ValueError(
                f"reasoning trace for run_id {run_id!r} already exists"
            ) from None

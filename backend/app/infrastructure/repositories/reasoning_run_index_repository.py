"""SQLAlchemy-backed reasoning run index repository."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from application.reasoning_run_index import (
    ReasoningRunIndex,
    ReasoningRunIndexRepository,
)
from backend.app.infrastructure.database.mappers.reasoning_run_index import (
    reasoning_run_index_to_domain,
    reasoning_run_index_to_model,
)
from backend.app.infrastructure.database.models.reasoning_run_index import (
    ReasoningRunIndexModel,
)
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository


class SqlAlchemyReasoningRunIndexRepository(
    SqlAlchemyRepository,
    ReasoningRunIndexRepository,
):
    """Persist reasoning run indexes in PostgreSQL through SQLAlchemy."""

    def get(self, run_id: str) -> ReasoningRunIndex | None:
        model = self._session.get(ReasoningRunIndexModel, run_id)
        if model is None:
            return None
        return reasoning_run_index_to_domain(model)

    def list(self) -> list[ReasoningRunIndex]:
        statement = select(ReasoningRunIndexModel).order_by(
            ReasoningRunIndexModel.run_id,
        )
        models = self._session.scalars(statement).all()
        return [reasoning_run_index_to_domain(model) for model in models]

    def save(self, index: ReasoningRunIndex) -> None:
        if self._session.get(ReasoningRunIndexModel, index.run_id) is not None:
            raise ValueError(
                f"reasoning run index with run_id {index.run_id!r} already exists"
            )

        model = reasoning_run_index_to_model(index)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            raise ValueError(
                f"reasoning run index with run_id {index.run_id!r} already exists"
            ) from None

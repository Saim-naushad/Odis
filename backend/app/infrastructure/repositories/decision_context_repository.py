"""SQLAlchemy-backed decision context repository."""

from sqlalchemy.exc import IntegrityError

from backend.app.infrastructure.database.mappers.decision_context import (
    decision_context_to_domain,
    decision_context_to_model,
)
from backend.app.infrastructure.database.models.decision_context import (
    DecisionContextModel,
)
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository
from domain.entities.decision_context import DecisionContext
from domain.repositories.decision_context_repository import DecisionContextRepository


class SqlAlchemyDecisionContextRepository(
    SqlAlchemyRepository,
    DecisionContextRepository,
):
    """Persist decision contexts in PostgreSQL through SQLAlchemy."""

    def get(self, context_id: str) -> DecisionContext | None:
        model = self._session.get(DecisionContextModel, context_id)
        if model is None:
            return None
        return decision_context_to_domain(model)

    def save(self, context: DecisionContext) -> None:
        if self._session.get(DecisionContextModel, context.id) is not None:
            raise ValueError(
                f"decision context with id {context.id!r} already exists"
            )

        model = decision_context_to_model(context)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            raise ValueError(
                f"decision context with id {context.id!r} already exists"
            ) from None

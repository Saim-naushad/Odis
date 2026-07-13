"""SQLAlchemy-backed investigation transition repository."""

from sqlalchemy import select

from backend.app.domain.investigation import InvestigationEvent
from backend.app.domain.repositories.investigation_repository import (
    InvestigationRepository,
)
from backend.app.infrastructure.database.mappers.investigation_transition import (
    investigation_transition_to_domain,
    investigation_transition_to_model,
)
from backend.app.infrastructure.database.models.investigation_transition import (
    InvestigationTransitionModel,
)
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository


class SqlAlchemyInvestigationRepository(SqlAlchemyRepository, InvestigationRepository):
    """Persist investigation transitions in PostgreSQL through SQLAlchemy."""

    def save(self, event: InvestigationEvent) -> None:
        if self._session.get(InvestigationTransitionModel, event.id) is not None:
            raise ValueError(
                f"investigation transition with id {event.id!r} already exists"
            )

        model = investigation_transition_to_model(event)
        self._session.add(model)
        self._session.flush()

    def get_latest_for_recommendation(
        self, recommendation_id: str
    ) -> InvestigationEvent | None:
        transitions = self.list_for_recommendation(recommendation_id)
        return transitions[-1] if transitions else None

    def list_for_recommendation(
        self, recommendation_id: str
    ) -> list[InvestigationEvent]:
        statement = (
            select(InvestigationTransitionModel)
            .where(
                InvestigationTransitionModel.recommendation_id == recommendation_id
            )
            .order_by(
                InvestigationTransitionModel.occurred_at,
                InvestigationTransitionModel.id,
            )
        )
        models = self._session.scalars(statement).all()
        return [investigation_transition_to_domain(model) for model in models]

"""SQLAlchemy-backed operational situation repository."""

from sqlalchemy.exc import IntegrityError

from backend.app.infrastructure.database.mappers.operational_situation import (
    situation_to_domain,
    situation_to_model,
)
from backend.app.infrastructure.database.models.operational_situation import (
    OperationalSituationModel,
)
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository
from domain.entities.operational_situation import OperationalSituation
from domain.repositories.situation_repository import SituationRepository


class SqlAlchemySituationRepository(SqlAlchemyRepository, SituationRepository):
    """Persist operational situations in PostgreSQL through SQLAlchemy."""

    def get(self, situation_id: str) -> OperationalSituation | None:
        model = self._session.get(OperationalSituationModel, situation_id)
        if model is None:
            return None
        return situation_to_domain(model)

    def save(self, situation: OperationalSituation) -> None:
        if self._session.get(OperationalSituationModel, situation.id) is not None:
            raise ValueError(
                f"situation with id {situation.id!r} already exists"
            )

        model = situation_to_model(situation)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            raise ValueError(
                f"situation with id {situation.id!r} already exists"
            ) from None

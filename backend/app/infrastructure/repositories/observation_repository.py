"""SQLAlchemy-backed observation repository."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.infrastructure.database.mappers.observation import (
    observation_to_domain,
    observation_to_model,
)
from backend.app.infrastructure.database.models.observation import ObservationModel
from backend.app.infrastructure.repositories.base import SqlAlchemyRepository
from domain.entities.observation import Observation
from domain.repositories.observation_repository import ObservationRepository


class SqlAlchemyObservationRepository(SqlAlchemyRepository, ObservationRepository):
    """Persist observations in PostgreSQL through SQLAlchemy."""

    def get(self, observation_id: str) -> Observation | None:
        model = self._session.get(ObservationModel, observation_id)
        if model is None:
            return None
        return observation_to_domain(model)

    def save(self, observation: Observation) -> None:
        if self._session.get(ObservationModel, observation.id) is not None:
            raise ValueError(f"observation with id {observation.id!r} already exists")

        model = observation_to_model(observation)
        self._session.add(model)
        try:
            self._session.flush()
        except IntegrityError:
            raise ValueError(
                f"observation with id {observation.id!r} already exists"
            ) from None

    def list(self) -> list[Observation]:
        statement = select(ObservationModel).order_by(
            ObservationModel.timestamp,
            ObservationModel.id,
        )
        models = self._session.scalars(statement).all()
        return [observation_to_domain(model) for model in models]

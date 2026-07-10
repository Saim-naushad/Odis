"""SQLAlchemy-backed observation repository."""

import builtins
from datetime import datetime

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

    def list_by_asset(self, asset_id: str) -> builtins.list[Observation]:
        return self.list_by_asset_in_time_range(asset_id)

    def list_by_asset_in_time_range(
        self,
        asset_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: str | None = None,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> builtins.list[Observation]:
        statement = select(ObservationModel).where(
            ObservationModel.asset_id == asset_id
        )

        if start is not None:
            statement = statement.where(ObservationModel.timestamp >= start)
        if end is not None:
            statement = statement.where(ObservationModel.timestamp <= end)
        if measurement_type is not None:
            statement = statement.where(
                ObservationModel.measurement_type_name == measurement_type
            )

        if newest_first:
            statement = statement.order_by(
                ObservationModel.timestamp.desc(),
                ObservationModel.id.desc(),
            )
        else:
            statement = statement.order_by(
                ObservationModel.timestamp,
                ObservationModel.id,
            )

        if limit is not None:
            statement = statement.limit(limit)

        models = self._session.scalars(statement).all()
        return [observation_to_domain(model) for model in models]

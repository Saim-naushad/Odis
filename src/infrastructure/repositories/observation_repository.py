import builtins
from datetime import datetime

from domain.entities.observation import Observation
from domain.repositories.observation_repository import ObservationRepository


class InMemoryObservationRepository(ObservationRepository):
    def __init__(self) -> None:
        self._storage: dict[str, Observation] = {}

    def get(self, observation_id: str) -> Observation | None:
        return self._storage.get(observation_id)

    def save(self, observation: Observation) -> None:
        if observation.id in self._storage:
            raise ValueError(f"observation with id {observation.id!r} already exists")
        self._storage[observation.id] = observation

    def list(self) -> list[Observation]:
        return sorted(
            self._storage.values(),
            key=lambda observation: (observation.timestamp, observation.id),
        )

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
        observations = [
            observation
            for observation in self.list()
            if observation.asset_id == asset_id
        ]

        if start is not None:
            observations = [
                observation
                for observation in observations
                if observation.timestamp >= start
            ]
        if end is not None:
            observations = [
                observation
                for observation in observations
                if observation.timestamp <= end
            ]
        if measurement_type is not None:
            observations = [
                observation
                for observation in observations
                if observation.measurement_type.name == measurement_type
            ]

        observations.sort(
            key=lambda observation: (observation.timestamp, observation.id),
            reverse=newest_first,
        )

        if limit is not None:
            observations = observations[:limit]

        return observations

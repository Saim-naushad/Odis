import builtins

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
        return [
            observation
            for observation in self.list()
            if observation.asset_id == asset_id
        ]

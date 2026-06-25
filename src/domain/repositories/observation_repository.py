from abc import ABC, abstractmethod

from domain.entities.observation import Observation


class ObservationRepository(ABC):
    @abstractmethod
    def get(self, observation_id: str) -> Observation | None:
        pass

    @abstractmethod
    def save(self, observation: Observation) -> None:
        pass

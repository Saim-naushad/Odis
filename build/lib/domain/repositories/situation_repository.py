from abc import ABC, abstractmethod

from domain.entities.operational_situation import OperationalSituation


class SituationRepository(ABC):
    @abstractmethod
    def get(self, situation_id: str) -> OperationalSituation | None:
        pass

    @abstractmethod
    def save(self, situation: OperationalSituation) -> None:
        pass

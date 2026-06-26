from abc import ABC, abstractmethod

from domain.entities.decision_context import DecisionContext


class DecisionContextRepository(ABC):
    @abstractmethod
    def get(self, context_id: str) -> DecisionContext | None:
        pass

    @abstractmethod
    def save(self, context: DecisionContext) -> None:
        pass

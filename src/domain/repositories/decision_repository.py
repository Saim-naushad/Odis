from abc import ABC, abstractmethod

from domain.entities.decision_context import DecisionContext
from domain.entities.decision_plan import DecisionPlan


class DecisionRepository(ABC):
    @abstractmethod
    def get_context(self, context_id: str) -> DecisionContext | None:
        pass

    @abstractmethod
    def save_context(self, context: DecisionContext) -> None:
        pass

    @abstractmethod
    def get_plan(self, plan_id: str) -> DecisionPlan | None:
        pass

    @abstractmethod
    def save_plan(self, plan: DecisionPlan) -> None:
        pass

from abc import ABC, abstractmethod

from domain.entities.decision_plan import DecisionPlan


class DecisionPlanRepository(ABC):
    @abstractmethod
    def get(self, plan_id: str) -> DecisionPlan | None:
        pass

    @abstractmethod
    def save(self, plan: DecisionPlan) -> None:
        pass

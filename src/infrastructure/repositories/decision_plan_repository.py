from domain.entities.decision_plan import DecisionPlan
from domain.repositories.decision_plan_repository import DecisionPlanRepository


class InMemoryDecisionPlanRepository(DecisionPlanRepository):
    def __init__(self) -> None:
        self._storage: dict[str, DecisionPlan] = {}

    def get(self, plan_id: str) -> DecisionPlan | None:
        return self._storage.get(plan_id)

    def save(self, plan: DecisionPlan) -> None:
        if plan.id in self._storage:
            raise ValueError(f"decision plan with id {plan.id!r} already exists")
        self._storage[plan.id] = plan

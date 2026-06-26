from domain.entities.decision_context import DecisionContext
from domain.repositories.decision_context_repository import DecisionContextRepository


class InMemoryDecisionContextRepository(DecisionContextRepository):
    def __init__(self) -> None:
        self._storage: dict[str, DecisionContext] = {}

    def get(self, context_id: str) -> DecisionContext | None:
        return self._storage.get(context_id)

    def save(self, context: DecisionContext) -> None:
        if context.id in self._storage:
            raise ValueError(f"decision context with id {context.id!r} already exists")
        self._storage[context.id] = context

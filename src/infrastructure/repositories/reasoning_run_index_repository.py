from application.reasoning_run_index import (
    ReasoningRunIndex,
    ReasoningRunIndexRepository,
)


class InMemoryReasoningRunIndexRepository(ReasoningRunIndexRepository):
    def __init__(self) -> None:
        self._storage: dict[str, ReasoningRunIndex] = {}

    def get(self, run_id: str) -> ReasoningRunIndex | None:
        return self._storage.get(run_id)

    def save(self, index: ReasoningRunIndex) -> None:
        if index.run_id in self._storage:
            raise ValueError(
                f"reasoning run index with run_id {index.run_id!r} already exists"
            )
        self._storage[index.run_id] = index

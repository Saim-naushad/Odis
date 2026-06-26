from domain.repositories.reasoning_run_repository import (
    PersistedReasoningRun,
    ReasoningRunRepository,
)


class InMemoryReasoningRunRepository(ReasoningRunRepository):
    def __init__(self) -> None:
        self._storage: dict[str, PersistedReasoningRun] = {}

    def get(self, run_id: str) -> PersistedReasoningRun | None:
        return self._storage.get(run_id)

    def save(self, run: PersistedReasoningRun) -> None:
        if run.id in self._storage:
            raise ValueError(f"reasoning run with id {run.id!r} already exists")
        self._storage[run.id] = run

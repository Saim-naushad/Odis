from application.reasoning_run_registry import ReasoningRunRegistryRepository
from domain.repositories.reasoning_run_repository import (
    PersistedReasoningRun,
    ReasoningRunRepository,
)


class ReasoningHistory:
    def __init__(
        self,
        reasoning_run_registry_repository: ReasoningRunRegistryRepository,
        reasoning_run_repository: ReasoningRunRepository,
    ) -> None:
        self._reasoning_run_registry_repository = reasoning_run_registry_repository
        self._reasoning_run_repository = reasoning_run_repository

    def list_runs(self) -> tuple[PersistedReasoningRun, ...]:
        runs: list[PersistedReasoningRun] = []
        for entry in self._reasoning_run_registry_repository.list():
            run = self._reasoning_run_repository.get(entry.run_id)
            if run is None:
                raise ValueError(
                    f"reasoning run with id {entry.run_id!r} does not exist"
                )
            runs.append(run)
        return tuple(runs)

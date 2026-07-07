from application.reasoning_run_registry import (
    ReasoningRunRegistryEntry,
    ReasoningRunRegistryRepository,
)


class InMemoryReasoningRunRegistryRepository(ReasoningRunRegistryRepository):
    def __init__(self) -> None:
        self._entries: list[ReasoningRunRegistryEntry] = []
        self._run_ids: set[str] = set()

    def add(self, entry: ReasoningRunRegistryEntry) -> None:
        if entry.run_id in self._run_ids:
            raise ValueError(
                f"reasoning run with id {entry.run_id!r} already registered"
            )
        self._run_ids.add(entry.run_id)
        self._entries.append(entry)

    def list(self) -> tuple[ReasoningRunRegistryEntry, ...]:
        return tuple(self._entries)

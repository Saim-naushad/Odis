from __future__ import annotations

from application.reasoning_run_index import (
    ReasoningRunIndex,
    ReasoningRunIndexRepository,
)


class InMemoryReasoningRunIndexRepository(ReasoningRunIndexRepository):
    def __init__(self) -> None:
        self._storage: dict[str, ReasoningRunIndex] = {}

    def get(self, run_id: str) -> ReasoningRunIndex | None:
        return self._storage.get(run_id)

    def list(self) -> list[ReasoningRunIndex]:
        return [self._storage[key] for key in sorted(self._storage)]

    def list_by_asset(
        self,
        asset_id: str,
        *,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> list[ReasoningRunIndex]:
        matches = [
            index for index in self._storage.values() if index.asset_id == asset_id
        ]
        matches.sort(key=lambda index: index.run_id, reverse=newest_first)
        if limit is not None:
            matches = matches[:limit]
        return matches

    def save(self, index: ReasoningRunIndex) -> None:
        if index.run_id in self._storage:
            raise ValueError(
                f"reasoning run index with run_id {index.run_id!r} already exists"
            )
        self._storage[index.run_id] = index

from __future__ import annotations

import builtins
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ReasoningRunIndex:
    run_id: str
    observation_ids: tuple[str, ...]
    situation_id: str
    context_id: str
    plan_id: str
    action_id: str
    outcome_id: str
    asset_id: str = ""


class ReasoningRunIndexRepository(ABC):
    @abstractmethod
    def get(self, run_id: str) -> ReasoningRunIndex | None:
        pass

    @abstractmethod
    def list(self) -> builtins.list[ReasoningRunIndex]:
        pass

    @abstractmethod
    def list_by_asset(
        self,
        asset_id: str,
        *,
        limit: int | None = None,
        newest_first: bool = True,
    ) -> builtins.list[ReasoningRunIndex]:
        """Return run indexes for an asset ordered by reasoning run start time."""
        pass

    @abstractmethod
    def save(self, index: ReasoningRunIndex) -> None:
        pass

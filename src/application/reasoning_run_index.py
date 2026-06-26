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


class ReasoningRunIndexRepository(ABC):
    @abstractmethod
    def get(self, run_id: str) -> ReasoningRunIndex | None:
        pass

    @abstractmethod
    def save(self, index: ReasoningRunIndex) -> None:
        pass

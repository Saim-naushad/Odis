from abc import ABC, abstractmethod

from application.reasoning_trace import ReasoningTrace


class ReasoningTraceRepository(ABC):
    @abstractmethod
    def get_by_run_id(self, run_id: str) -> ReasoningTrace | None:
        pass

    @abstractmethod
    def save(self, run_id: str, trace: ReasoningTrace) -> None:
        pass

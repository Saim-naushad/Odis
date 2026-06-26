from abc import ABC, abstractmethod
from datetime import datetime
from typing import Protocol


class PersistedReasoningRun(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def started_at(self) -> datetime: ...


class ReasoningRunRepository(ABC):
    @abstractmethod
    def get(self, run_id: str) -> PersistedReasoningRun | None:
        pass

    @abstractmethod
    def save(self, run: PersistedReasoningRun) -> None:
        pass

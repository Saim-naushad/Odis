from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReasoningRunRegistryEntry:
    run_id: str
    started_at: datetime


class ReasoningRunRegistryRepository(ABC):
    @abstractmethod
    def add(self, entry: ReasoningRunRegistryEntry) -> None:
        pass

    @abstractmethod
    def list(self) -> tuple[ReasoningRunRegistryEntry, ...]:
        pass

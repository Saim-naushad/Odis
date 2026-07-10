import builtins
from abc import ABC, abstractmethod
from datetime import datetime

from domain.entities.observation import Observation


class ObservationRepository(ABC):
    @abstractmethod
    def get(self, observation_id: str) -> Observation | None:
        pass

    @abstractmethod
    def save(self, observation: Observation) -> None:
        pass

    @abstractmethod
    def list(self) -> list[Observation]:
        pass

    @abstractmethod
    def list_by_asset(self, asset_id: str) -> builtins.list[Observation]:
        pass

    @abstractmethod
    def list_by_asset_in_time_range(
        self,
        asset_id: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        measurement_type: str | None = None,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> builtins.list[Observation]:
        """Return observations for an asset filtered by optional time and metric."""
        pass

from typing import Protocol

from domain.entities.observation import Observation


class ObservationSource(Protocol):
    def read(self) -> tuple[Observation, ...]: ...

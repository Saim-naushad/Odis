from collections.abc import Iterable

from domain.entities.observation import Observation


class StaticObservationSource:
    def __init__(self, observations: Iterable[Observation]) -> None:
        self._observations = tuple(observations)

    def read(self) -> tuple[Observation, ...]:
        return self._observations

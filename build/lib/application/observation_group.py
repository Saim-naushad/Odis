from dataclasses import dataclass, field

from application.measurement_index import MeasurementIndex
from domain.entities.observation import Observation


@dataclass(frozen=True)
class ObservationGroup:
    asset_id: str
    observations: tuple[Observation, ...]
    _measurements: MeasurementIndex = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.observations:
            raise ValueError("at least one observation is required")

        if any(
            observation.asset_id != self.asset_id for observation in self.observations
        ):
            raise ValueError("all observations must share the same asset_id")

        object.__setattr__(self, "_measurements", MeasurementIndex.from_group(self))

    @property
    def measurements(self) -> MeasurementIndex:
        return self._measurements

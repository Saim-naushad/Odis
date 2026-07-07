from dataclasses import dataclass

from domain.entities.observation import Observation


@dataclass(frozen=True)
class ObservationGroup:
    asset_id: str
    observations: tuple[Observation, ...]

    def __post_init__(self) -> None:
        if not self.observations:
            raise ValueError("at least one observation is required")

        if any(
            observation.asset_id != self.asset_id for observation in self.observations
        ):
            raise ValueError("all observations must share the same asset_id")

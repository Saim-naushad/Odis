from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType

if TYPE_CHECKING:
    from application.observation_group import ObservationGroup


@dataclass(frozen=True)
class MeasurementIndex:
    _by_type: Mapping[MeasurementType, tuple[Observation, ...]]

    @classmethod
    def from_group(cls, group: ObservationGroup) -> MeasurementIndex:
        buckets: dict[MeasurementType, list[Observation]] = {}

        for observation in group.observations:
            measurement_type = observation.measurement_type
            if measurement_type not in buckets:
                buckets[measurement_type] = []
            buckets[measurement_type].append(observation)

        frozen = MappingProxyType(
            {
                measurement_type: tuple(observations)
                for measurement_type, observations in buckets.items()
            }
        )
        return cls(_by_type=frozen)

    def get(self, measurement_type: MeasurementType) -> tuple[Observation, ...]:
        return self._by_type.get(measurement_type, ())

    def measurement_types(self) -> tuple[MeasurementType, ...]:
        return tuple(self._by_type.keys())


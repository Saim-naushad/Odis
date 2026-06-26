from dataclasses import dataclass

from domain.value_objects.measurement_type import MeasurementType
from domain.value_objects.variation_level import VariationLevel


@dataclass(frozen=True)
class DetectedVariation:
    asset_id: str
    measurement_type: MeasurementType
    level: VariationLevel

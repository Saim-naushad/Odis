from dataclasses import dataclass

from domain.value_objects.measurement_type import MeasurementType
from domain.value_objects.trend_direction import TrendDirection


@dataclass(frozen=True)
class DetectedTrend:
    direction: TrendDirection
    asset_id: str
    measurement_type: MeasurementType

from dataclasses import dataclass
from datetime import datetime

from domain.value_objects.measurement_type import MeasurementType


@dataclass(frozen=True)
class Observation:
    """A measurement recorded from the environment at a point in time.

    Immutable after creation. Identity and content are fixed at recording time.

    Immutable fields: id, asset_id, timestamp, measurement_type, value, unit.
    Evolving fields: none.

    Owned relationships: none.
    Referenced relationships: Asset (asset_id), MeasurementType (measurement_type).
    """

    id: str
    asset_id: str
    timestamp: datetime
    measurement_type: MeasurementType
    value: float
    unit: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.asset_id:
            raise ValueError("asset_id must not be empty")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if not self.unit:
            raise ValueError("unit must not be empty")

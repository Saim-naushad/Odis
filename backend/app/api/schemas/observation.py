"""Observation API request and response schemas."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType


class ObservationCreate(BaseModel):
    """Payload for creating a persisted observation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "obs-001",
                "asset_id": "asset-stack-1",
                "timestamp": "2026-01-01T12:00:00Z",
                "measurement_type": "temperature",
                "value": 42.5,
                "unit": "celsius",
            }
        }
    )

    id: str = Field(min_length=1, description="Unique observation identifier")
    asset_id: str = Field(
        min_length=1,
        description="Asset that produced the measurement",
    )
    timestamp: datetime = Field(description="Timezone-aware measurement timestamp")
    measurement_type: str = Field(
        min_length=1,
        description="Measurement type name (for example, temperature or pressure)",
    )
    value: float = Field(description="Recorded measurement value")
    unit: str = Field(min_length=1, description="Measurement unit")

    def to_domain(self) -> Observation:
        """Translate the API payload into a domain observation."""
        return Observation(
            id=self.id,
            asset_id=self.asset_id,
            timestamp=self.timestamp,
            measurement_type=MeasurementType(name=self.measurement_type),
            value=self.value,
            unit=self.unit,
        )


class ObservationResponse(BaseModel):
    """Serialized observation returned by the platform API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "obs-001",
                "asset_id": "asset-stack-1",
                "timestamp": "2026-01-01T12:00:00Z",
                "measurement_type": "temperature",
                "value": 42.5,
                "unit": "celsius",
            }
        }
    )

    id: str
    asset_id: str
    timestamp: datetime
    measurement_type: str
    value: float
    unit: str

    @classmethod
    def from_domain(cls, observation: Observation) -> Self:
        """Translate a domain observation into an API response."""
        return cls(
            id=observation.id,
            asset_id=observation.asset_id,
            timestamp=observation.timestamp,
            measurement_type=observation.measurement_type.name,
            value=observation.value,
            unit=observation.unit,
        )

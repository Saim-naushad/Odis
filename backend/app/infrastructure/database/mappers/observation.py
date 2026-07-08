"""Mapping between domain observations and ORM models."""

from datetime import UTC, datetime

from backend.app.infrastructure.database.models.observation import ObservationModel
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp


def observation_to_model(observation: Observation) -> ObservationModel:
    """Map a domain observation to its SQLAlchemy representation."""
    return ObservationModel(
        id=observation.id,
        asset_id=observation.asset_id,
        timestamp=observation.timestamp,
        measurement_type_name=observation.measurement_type.name,
        value=observation.value,
        unit=observation.unit,
    )


def observation_to_domain(model: ObservationModel) -> Observation:
    """Map a SQLAlchemy observation row to the domain entity."""
    return Observation(
        id=model.id,
        asset_id=model.asset_id,
        timestamp=_ensure_utc(model.timestamp),
        measurement_type=MeasurementType(name=model.measurement_type_name),
        value=model.value,
        unit=model.unit,
    )

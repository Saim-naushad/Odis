from datetime import UTC, datetime, timedelta
from typing import Any

from domain.entities.asset import Asset
from domain.entities.observation import Observation
from domain.entities.operational_goal import OperationalGoal
from domain.value_objects.location import Location
from domain.value_objects.measurement_type import MeasurementType

DEFAULT_TIMESTAMP = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def build_measurement_type(**overrides: Any) -> MeasurementType:
    defaults: dict[str, Any] = {"name": "temperature"}
    defaults.update(overrides)
    return MeasurementType(name=defaults["name"])


def build_asset(**overrides: Any) -> Asset:
    defaults: dict[str, Any] = {
        "id": "asset-1",
        "name": "Test Asset",
        "type": "equipment",
        "location": Location(identifier="site-1"),
    }
    defaults.update(overrides)
    return Asset(
        id=defaults["id"],
        name=defaults["name"],
        type=defaults["type"],
        location=defaults["location"],
    )


def build_goal(**overrides: Any) -> OperationalGoal:
    defaults: dict[str, Any] = {
        "id": "goal-1",
        "description": "Test operational goal",
    }
    defaults.update(overrides)
    return OperationalGoal(
        id=defaults["id"],
        description=defaults["description"],
    )


def build_observation(**overrides: Any) -> Observation:
    defaults: dict[str, Any] = {
        "id": "obs-1",
        "asset_id": "asset-1",
        "timestamp": DEFAULT_TIMESTAMP,
        "measurement_type": build_measurement_type(),
        "value": 0.0,
        "unit": "unit",
    }
    defaults.update(overrides)
    return Observation(
        id=defaults["id"],
        asset_id=defaults["asset_id"],
        timestamp=defaults["timestamp"],
        measurement_type=defaults["measurement_type"],
        value=defaults["value"],
        unit=defaults["unit"],
    )


def build_observation_sequence(
    values: list[float] | tuple[float, ...],
    *,
    asset_id: str = "asset-1",
    measurement_type: MeasurementType | None = None,
    unit: str = "unit",
    start: datetime | None = None,
    interval_hours: int = 1,
    id_prefix: str = "obs",
) -> tuple[Observation, ...]:
    base_time = start or DEFAULT_TIMESTAMP
    resolved_measurement_type = measurement_type or build_measurement_type()

    return tuple(
        build_observation(
            id=f"{id_prefix}-{index}",
            asset_id=asset_id,
            timestamp=base_time + timedelta(hours=interval_hours * index),
            measurement_type=resolved_measurement_type,
            value=value,
            unit=unit,
        )
        for index, value in enumerate(values)
    )

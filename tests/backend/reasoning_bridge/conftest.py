"""Shared fixtures for reasoning-bridge tests: an in-memory sqlite
session factory, matching `tests/backend/test_investigation.py`'s own
pattern."""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from domain.entities.observation import Observation
from domain.value_objects.measurement_type import MeasurementType


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://")


@pytest.fixture
def session_factory(
    sqlite_settings: Settings,
) -> Generator[Callable[[], Session], None, None]:
    engine = create_db_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        engine.dispose()


def make_observation(
    *,
    asset_id: str,
    measurement_type: str,
    value: float,
    unit: str,
    timestamp: datetime,
    observation_id: str | None = None,
) -> Observation:
    suffix = observation_id or f"{measurement_type}-{timestamp.isoformat()}"
    return Observation(
        id=f"obs-{asset_id}-{suffix}",
        asset_id=asset_id,
        timestamp=timestamp,
        measurement_type=MeasurementType(name=measurement_type),
        value=value,
        unit=unit,
    )

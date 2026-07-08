"""Observation persistence specifications for the ODIS platform backend."""

from collections.abc import Generator

import pytest
from sqlalchemy.orm import Session

from backend.app.infrastructure.config.settings import Settings
from backend.app.infrastructure.database import models as _models  # noqa: F401
from backend.app.infrastructure.database.base import Base
from backend.app.infrastructure.database.mappers.observation import (
    observation_to_domain,
    observation_to_model,
)
from backend.app.infrastructure.database.models.observation import ObservationModel
from backend.app.infrastructure.database.session import (
    create_db_engine,
    create_session_factory,
)
from backend.app.infrastructure.repositories.observation_repository import (
    SqlAlchemyObservationRepository,
)
from domain.entities.observation import Observation
from tests.builders import DEFAULT_TIMESTAMP, build_observation


@pytest.fixture
def sqlite_settings() -> Settings:
    return Settings(database_url="sqlite://")


@pytest.fixture
def db_session(sqlite_settings: Settings) -> Generator[Session, None, None]:
    engine = create_db_engine(sqlite_settings)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def observation_repository(db_session: Session) -> SqlAlchemyObservationRepository:
    return SqlAlchemyObservationRepository(db_session)


def test_save_observation(
    observation_repository: SqlAlchemyObservationRepository,
) -> None:
    observation = build_observation()

    observation_repository.save(observation)

    assert observation_repository.get(observation.id) is not None


def test_retrieve_observation(
    observation_repository: SqlAlchemyObservationRepository,
) -> None:
    observation = build_observation(id="obs-retrieve", value=42.5, unit="celsius")
    observation_repository.save(observation)

    retrieved = observation_repository.get("obs-retrieve")

    assert retrieved is not None
    assert retrieved.id == "obs-retrieve"
    assert retrieved.value == 42.5
    assert retrieved.unit == "celsius"


def test_get_unknown_id_returns_none(
    observation_repository: SqlAlchemyObservationRepository,
) -> None:
    assert observation_repository.get("missing-id") is None


def test_multiple_observations(
    observation_repository: SqlAlchemyObservationRepository,
) -> None:
    first = build_observation(id="obs-1", value=1.0)
    second = build_observation(id="obs-2", value=2.0)
    third = build_observation(id="obs-3", value=3.0)

    observation_repository.save(first)
    observation_repository.save(second)
    observation_repository.save(third)

    observations = observation_repository.list()

    assert len(observations) == 3
    assert {observation.id for observation in observations} == {
        "obs-1",
        "obs-2",
        "obs-3",
    }


def test_repository_returns_domain_objects(
    observation_repository: SqlAlchemyObservationRepository,
) -> None:
    observation = build_observation()
    observation_repository.save(observation)

    retrieved = observation_repository.get(observation.id)

    assert isinstance(retrieved, Observation)


def test_round_trip_mapping_correctness(
    observation_repository: SqlAlchemyObservationRepository,
) -> None:
    observation = build_observation(
        id="obs-round-trip",
        asset_id="asset-round-trip",
        timestamp=DEFAULT_TIMESTAMP,
        value=99.9,
        unit="bar",
    )
    observation_repository.save(observation)

    retrieved = observation_repository.get("obs-round-trip")

    assert retrieved == observation


def test_duplicate_id_is_rejected(
    observation_repository: SqlAlchemyObservationRepository,
) -> None:
    observation_repository.save(build_observation(id="entity-1", value=10.0))

    with pytest.raises(ValueError, match="already exists"):
        observation_repository.save(build_observation(id="entity-1", value=20.0))


def test_observation_to_model_maps_all_fields() -> None:
    observation = build_observation(
        id="obs-map",
        asset_id="asset-map",
        value=12.3,
        unit="volts",
    )

    model = observation_to_model(observation)

    assert isinstance(model, ObservationModel)
    assert model.id == "obs-map"
    assert model.asset_id == "asset-map"
    assert model.timestamp == observation.timestamp
    assert model.measurement_type_name == observation.measurement_type.name
    assert model.value == 12.3
    assert model.unit == "volts"


def test_observation_to_domain_maps_all_fields() -> None:
    observation = build_observation(id="obs-domain")
    model = observation_to_model(observation)

    domain = observation_to_domain(model)

    assert domain == observation

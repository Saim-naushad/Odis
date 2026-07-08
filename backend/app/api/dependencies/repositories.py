"""Repository dependency providers for route handlers."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.api.dependencies.database import get_db_session
from backend.app.infrastructure.repositories.observation_repository import (
    SqlAlchemyObservationRepository,
)
from domain.repositories.observation_repository import ObservationRepository


def get_observation_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> ObservationRepository:
    """Provide a request-scoped observation repository."""
    return SqlAlchemyObservationRepository(session)

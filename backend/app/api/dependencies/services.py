"""Application service dependency providers for route handlers."""

from typing import Annotated

from fastapi import Depends

from backend.app.api.dependencies.repositories import get_observation_repository
from backend.app.application.observation_service import ObservationService
from domain.repositories.observation_repository import ObservationRepository


def get_observation_service(
    repository: Annotated[ObservationRepository, Depends(get_observation_repository)],
) -> ObservationService:
    """Provide a request-scoped observation application service."""
    return ObservationService(repository)

"""Observation persistence endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies.services import get_observation_service
from backend.app.api.schemas.observation import (
    ObservationAcceptedResponse,
    ObservationCreate,
    ObservationResponse,
)
from backend.app.application.exceptions import ObservationAlreadyExistsError
from backend.app.application.observation_service import ObservationService

router = APIRouter(prefix="/observations", tags=["observations"])


@router.post(
    "",
    response_model=ObservationAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create an observation",
    response_description=(
        "The persisted observation and enqueued reasoning job identifier."
    ),
)
def create_observation(
    payload: ObservationCreate,
    service: Annotated[ObservationService, Depends(get_observation_service)],
) -> ObservationAcceptedResponse:
    """Validate and persist a new operational observation."""
    try:
        result = service.create(payload.to_domain())
    except ObservationAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return ObservationAcceptedResponse.from_create_result(result)


@router.get(
    "",
    response_model=list[ObservationResponse],
    summary="List observations",
    response_description="All persisted observations in stable order.",
)
def list_observations(
    service: Annotated[ObservationService, Depends(get_observation_service)],
) -> list[ObservationResponse]:
    """Return every stored observation."""
    observations = service.list_observations()
    return [
        ObservationResponse.from_domain(observation) for observation in observations
    ]


@router.get(
    "/{observation_id}",
    response_model=ObservationResponse,
    summary="Get an observation",
    response_description="The requested observation.",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Observation not found"}},
)
def get_observation(
    observation_id: str,
    service: Annotated[ObservationService, Depends(get_observation_service)],
) -> ObservationResponse:
    """Return a single observation by identifier."""
    observation = service.get(observation_id)
    if observation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"observation with id {observation_id!r} not found",
        )
    return ObservationResponse.from_domain(observation)

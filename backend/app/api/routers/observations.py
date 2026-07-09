"""Observation persistence endpoints."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from backend.app.api.dependencies.services import (
    get_observation_service,
    get_reasoning_task_runner,
)
from backend.app.api.schemas.observation import ObservationCreate, ObservationResponse
from backend.app.application.exceptions import ObservationAlreadyExistsError
from backend.app.application.observation_service import ObservationService
from backend.app.application.reasoning_task_runner import ReasoningTaskRunner
from backend.app.infrastructure.logging import get_request_id

router = APIRouter(prefix="/observations", tags=["observations"])


@router.post(
    "",
    response_model=ObservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an observation",
    response_description="The persisted observation.",
)
def create_observation(
    payload: ObservationCreate,
    background_tasks: BackgroundTasks,
    service: Annotated[ObservationService, Depends(get_observation_service)],
    reasoning_runner: Annotated[
        ReasoningTaskRunner, Depends(get_reasoning_task_runner)
    ],
) -> ObservationResponse:
    """Validate and persist a new operational observation."""
    try:
        observation = service.create(payload.to_domain())
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

    background_tasks.add_task(
        reasoning_runner.run_for_asset,
        observation.asset_id,
        get_request_id(),
    )
    return ObservationResponse.from_domain(observation)


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

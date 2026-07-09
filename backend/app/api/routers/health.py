"""Production health, readiness, and liveness endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from backend.app.api.dependencies.services import get_health_service
from backend.app.api.schemas.health import HealthResponse, LiveResponse, ReadyResponse
from backend.app.application.health_service import HealthService, to_payload

router = APIRouter(tags=["health"])


@router.get("/live", response_model=LiveResponse, summary="Liveness probe")
def live(
    service: Annotated[HealthService, Depends(get_health_service)],
) -> LiveResponse:
    """Verify only that the application process is alive."""
    return LiveResponse(**to_payload(service.live()))


@router.get("/ready", response_model=ReadyResponse, summary="Readiness probe")
def ready(
    response: Response,
    service: Annotated[HealthService, Depends(get_health_service)],
) -> ReadyResponse:
    """Verify required dependencies before accepting traffic."""
    status_code, result = service.ready()
    response.status_code = status_code
    return ReadyResponse(**to_payload(result))


@router.get("/health", response_model=HealthResponse, summary="Overall health summary")
def health(
    response: Response,
    service: Annotated[HealthService, Depends(get_health_service)],
) -> HealthResponse:
    """Return an operational health summary suitable for production."""
    status_code, result = service.health()
    response.status_code = status_code
    return HealthResponse(**to_payload(result))

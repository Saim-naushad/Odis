"""Health check endpoints."""

from fastapi import APIRouter

from backend.app.api.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return a simple liveness indicator for the platform API."""
    return HealthResponse(status="ok")

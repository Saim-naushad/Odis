"""Health check response schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Liveness response for platform health checks."""

    status: str

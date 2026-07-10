"""Health check response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class DependencyCheckResponse(BaseModel):
    status: str = Field(..., examples=["healthy", "degraded", "unhealthy"])
    required: bool
    latency_ms: int | None = None
    details: str | None = None


class LiveResponse(BaseModel):
    status: str = Field(..., examples=["alive"])


class ReadyResponse(BaseModel):
    status: str = Field(..., examples=["ready", "not_ready"])
    checks: dict[str, DependencyCheckResponse] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["healthy", "degraded", "unhealthy"])
    version: str
    environment: str
    reasoning_engine: str
    uptime_seconds: int
    checks: dict[str, DependencyCheckResponse]


def as_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump()

"""Health check response schemas."""

from typing import Any

from pydantic import BaseModel, Field


class LiveResponse(BaseModel):
    status: str = Field(..., examples=["alive"])


class ReadyResponse(BaseModel):
    status: str = Field(..., examples=["ready", "not_ready"])
    checks: dict[str, str] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["healthy", "unhealthy"])
    version: str
    environment: str
    reasoning_engine: str
    uptime_seconds: int
    checks: dict[str, str]


def as_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump()

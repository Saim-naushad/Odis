"""Pydantic schemas for API request and response models."""

from backend.app.api.schemas.health import HealthResponse
from backend.app.api.schemas.platform import PlatformMetadataResponse

__all__ = ["HealthResponse", "PlatformMetadataResponse"]

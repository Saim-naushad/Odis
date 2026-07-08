"""Platform metadata endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from backend.app.api.dependencies.settings import get_app_settings
from backend.app.api.schemas.platform import PlatformMetadataResponse
from backend.app.infrastructure.config.settings import Settings

router = APIRouter(tags=["platform"])

REASONING_ENGINE_VERSION = "v1"
PLATFORM_PHASE = "phase-2"


@router.get("/", response_model=PlatformMetadataResponse)
def platform_metadata(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> PlatformMetadataResponse:
    """Return basic metadata about the ODIS platform."""
    return PlatformMetadataResponse(
        platform_name=settings.app_name,
        reasoning_engine_version=REASONING_ENGINE_VERSION,
        platform_phase=PLATFORM_PHASE,
    )

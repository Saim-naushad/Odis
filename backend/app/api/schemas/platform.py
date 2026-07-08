"""Platform metadata response schemas."""

from pydantic import BaseModel


class PlatformMetadataResponse(BaseModel):
    """Basic metadata describing the ODIS platform."""

    platform_name: str
    reasoning_engine_version: str
    platform_phase: str

"""Settings dependency for route handlers."""

from fastapi import Request

from backend.app.infrastructure.config.settings import Settings, get_settings


def get_app_settings(request: Request) -> Settings:
    """Provide application settings to route handlers."""
    configured_settings = getattr(request.app.state, "settings", None)
    if isinstance(configured_settings, Settings):
        return configured_settings
    return get_settings()

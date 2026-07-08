"""FastAPI dependency providers."""

from backend.app.api.dependencies.database import get_db_session
from backend.app.api.dependencies.repositories import get_observation_repository
from backend.app.api.dependencies.services import get_observation_service
from backend.app.api.dependencies.settings import get_app_settings

__all__ = [
    "get_app_settings",
    "get_db_session",
    "get_observation_repository",
    "get_observation_service",
]

"""API route modules."""

from backend.app.api.routers.health import router as health_router
from backend.app.api.routers.monitoring import router as monitoring_router
from backend.app.api.routers.observations import router as observations_router
from backend.app.api.routers.platform import router as platform_router

__all__ = [
    "health_router",
    "monitoring_router",
    "observations_router",
    "platform_router",
]

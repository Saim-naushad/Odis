"""API route modules."""

from backend.app.api.routers.health import router as health_router
from backend.app.api.routers.platform import router as platform_router

__all__ = ["health_router", "platform_router"]

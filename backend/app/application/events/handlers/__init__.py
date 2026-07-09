"""Domain event handlers."""

from backend.app.application.events.handlers.twin_cache_invalidation_handler import (
    DigitalTwinCacheInvalidationHandler,
)

__all__ = ["DigitalTwinCacheInvalidationHandler"]

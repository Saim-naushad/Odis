"""Platform persistence repository abstractions."""

from backend.app.infrastructure.repositories.base import SqlAlchemyRepository
from backend.app.infrastructure.repositories.protocols import PlatformRepository

__all__ = [
    "PlatformRepository",
    "SqlAlchemyRepository",
]

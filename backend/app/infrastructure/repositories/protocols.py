"""Repository interface contracts for platform persistence."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class PlatformRepository(Protocol):
    """Marker protocol for platform repository implementations.

    Concrete repositories implement domain repository interfaces from
    ``src/domain/repositories`` and are registered here as infrastructure
    adapters. Future entity-specific repositories (observations, reasoning
    runs, etc.) will subclass :class:`SqlAlchemyRepository` and satisfy both
    their domain contract and this protocol.
    """

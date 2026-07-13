"""Repository contract for append-only investigation lifecycle transitions."""

from __future__ import annotations

from typing import Protocol

from backend.app.domain.investigation import InvestigationEvent


class InvestigationRepository(Protocol):
    """Persist and query investigation transitions by recommendation."""

    def save(self, event: InvestigationEvent) -> None:
        """Persist a new investigation transition."""

    def get_latest_for_recommendation(
        self, recommendation_id: str
    ) -> InvestigationEvent | None:
        """Return the most recent transition for a recommendation, if any."""

    def list_for_recommendation(
        self, recommendation_id: str
    ) -> list[InvestigationEvent]:
        """Return all transitions for a recommendation, oldest first."""

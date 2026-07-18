from __future__ import annotations

from typing import Protocol

from application.reasoning.context import ReasoningContext


class ReasoningStage(Protocol):
    """Minimal synchronous stage contract for the reasoning pipeline."""

    name: str

    def run(self, context: ReasoningContext) -> ReasoningContext:
        """Return a new context with this stage's outputs enriched."""

from __future__ import annotations

from dataclasses import dataclass

from domain.reasoning.evidence import Evidence
from domain.reasoning.hypothesis import Hypothesis


@dataclass(frozen=True, slots=True)
class Explanation:
    """Presentation-layer narrative generated after factual assessment outputs."""

    summary: str
    evidence: tuple[Evidence, ...]
    hypotheses_considered: tuple[Hypothesis, ...]
    caveats: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.summary:
            raise ValueError("summary must not be empty")

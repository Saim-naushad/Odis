"""Explainable reasoning primitives for deterministic decisions.

Reasoning Engine v2 introduces explicit, immutable concepts that make decisions
auditable without relying on probabilistic models or LLMs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Evidence:
    """A single, user-facing piece of evidence supporting a recommendation."""

    id: str
    description: str
    measurement_type: str
    observed_value: str
    contribution_weight: float  # 0..1

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.description:
            raise ValueError("description must not be empty")
        if not self.measurement_type:
            raise ValueError("measurement_type must not be empty")
        if not self.observed_value:
            raise ValueError("observed_value must not be empty")
        if not (0.0 <= self.contribution_weight <= 1.0):
            raise ValueError("contribution_weight must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class ConfidenceScore:
    """Deterministic confidence score for a recommendation."""

    value: int  # 0..100
    rationale: str

    def __post_init__(self) -> None:
        if not (0 <= self.value <= 100):
            raise ValueError("value must be between 0 and 100")
        if not self.rationale:
            raise ValueError("rationale must not be empty")


@dataclass(frozen=True, slots=True)
class AlternativeHypothesis:
    """A plausible, deterministic alternative explanation."""

    title: str
    reason: str
    confidence: int  # 0..100

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError("title must not be empty")
        if not self.reason:
            raise ValueError("reason must not be empty")
        if not (0 <= self.confidence <= 100):
            raise ValueError("confidence must be between 0 and 100")


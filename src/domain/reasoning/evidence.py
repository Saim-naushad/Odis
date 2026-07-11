from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EvidenceRole(StrEnum):
    PRIMARY_SUPPORT = "primary_support"
    CORROBORATING = "corroborating"
    CONTRADICTING = "contradicting"
    CONTEXT = "context"


class EvidenceSourceSignal(StrEnum):
    LATEST_READING = "latest_reading"
    DETECTED_TREND = "detected_trend"
    DETECTED_VARIATION = "detected_variation"
    RECENT_DELTA = "recent_delta"
    SAMPLE_SUPPORT = "sample_support"
    RELATIONSHIP_CORRELATION = "relationship_correlation"
    RELATIONSHIP_CONTRADICTION = "relationship_contradiction"


@dataclass(frozen=True, slots=True)
class Evidence:
    """Interpreted support derived from observations and extracted signals."""

    id: str
    description: str
    source_signal: EvidenceSourceSignal
    measurement_type: str
    observed_value: str
    role: EvidenceRole
    weight: float

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.description:
            raise ValueError("description must not be empty")
        if not self.measurement_type:
            raise ValueError("measurement_type must not be empty")
        if not self.observed_value:
            raise ValueError("observed_value must not be empty")
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError("weight must be between 0 and 1")

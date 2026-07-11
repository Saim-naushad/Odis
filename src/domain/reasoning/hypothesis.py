from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class HypothesisKind(StrEnum):
    UNKNOWN = "unknown"
    SENSOR_DRIFT = "sensor_drift"
    LOAD_CHANGE = "load_change"
    COOLING_DEGRADATION = "cooling_degradation"
    HYDROGEN_SUPPLY = "hydrogen_supply"


_HYPOTHESIS_TITLES: dict[HypothesisKind, str] = {
    HypothesisKind.UNKNOWN: "Unknown cause",
    HypothesisKind.SENSOR_DRIFT: "Sensor drift",
    HypothesisKind.LOAD_CHANGE: "Load change",
    HypothesisKind.COOLING_DEGRADATION: "Cooling degradation",
    HypothesisKind.HYDROGEN_SUPPLY: "Hydrogen supply issue",
}


def hypothesis_display_title(kind: HypothesisKind) -> str:
    """Return a human-readable title for a canonical hypothesis kind."""
    return _HYPOTHESIS_TITLES[kind]


@dataclass(frozen=True, slots=True)
class Hypothesis:
    id: str
    kind: HypothesisKind
    rationale: str
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must not be empty")
        if not self.rationale:
            raise ValueError("rationale must not be empty")

    @property
    def display_title(self) -> str:
        return hypothesis_display_title(self.kind)

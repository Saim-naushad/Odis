from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConfidenceBreakdown:
    """Auditable confidence components for a produced assessment.

    Future ConfidenceStage scores confidence in the assessment itself, not
    recommendation severity.
    """

    base: int
    support: int
    consistency: int
    trend_consistency: int
    sustained_bonus: int
    penalties: int
    total: int
    rationale: str

    def __post_init__(self) -> None:
        for field_name in (
            "base",
            "support",
            "consistency",
            "trend_consistency",
            "sustained_bonus",
            "penalties",
            "total",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int):
                raise ValueError(f"{field_name} must be an integer")
        if not (0 <= self.total <= 100):
            raise ValueError("total must be between 0 and 100")
        if not self.rationale:
            raise ValueError("rationale must not be empty")

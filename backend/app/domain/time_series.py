"""Deterministic, explainable time-series primitives.

ODIS uses time-series analysis to reason about asset behavior over time rather
than isolated point observations.

No forecasting. No ML. No probabilistic models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TrendDirection = Literal["rising", "falling", "stable"]


@dataclass(frozen=True, slots=True)
class TrendAnalysis:
    """Explainable analysis of recent observations for a single signal.

    Scores are normalized to 0..100 for operator readability:
    - stability_score: higher means more consistent / monotonic / predictable.
    - volatility_score: higher means more noisy / erratic change between samples.
    """

    direction: TrendDirection
    rate_of_change: float
    stability_score: int  # 0..100
    volatility_score: int  # 0..100
    observation_window: int
    summary: str

    def __post_init__(self) -> None:
        if self.direction not in ("rising", "falling", "stable"):
            raise ValueError("direction must be one of: rising, falling, stable")
        if not (0 <= self.stability_score <= 100):
            raise ValueError("stability_score must be between 0 and 100")
        if not (0 <= self.volatility_score <= 100):
            raise ValueError("volatility_score must be between 0 and 100")
        if self.observation_window < 0:
            raise ValueError("observation_window must be >= 0")
        if not self.summary:
            raise ValueError("summary must not be empty")


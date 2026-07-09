"""Deterministic time-series analysis over recent observations.

This module intentionally keeps algorithms simple, auditable, and stable:
- No forecasting (we only describe the recent window).
- No machine learning.
- No probabilistic reasoning.

The analysis is used as an explainable signal for confidence, evidence, and
timeline events.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt

from backend.app.domain.time_series import TrendAnalysis, TrendDirection
from domain.entities.observation import Observation


@dataclass(frozen=True, slots=True)
class TrendDiagnostics:
    direction: TrendDirection
    rate_of_change: float
    monotonicity: float  # 0..1
    volatility_norm: float  # 0..1
    stability_score: int  # 0..100
    volatility_score: int  # 0..100


def analyze_trend(
    observations: Sequence[Observation],
    *,
    observation_window: int = 5,
    measurement_label: str | None = None,
) -> TrendAnalysis:
    """Analyze the most recent observations.

    Args:
        observations: Observations for a single measurement type. May contain more
            than the requested window; ordering does not matter.
        observation_window: Max number of most recent observations to analyze.
        measurement_label: Optional label for building operator-facing summaries.
    """

    if observation_window <= 0:
        raise ValueError("observation_window must be > 0")

    ordered = list(observations)
    ordered.sort(key=lambda obs: (obs.timestamp, obs.id))
    windowed = ordered[-observation_window:]

    if len(windowed) < 2:
        label = measurement_label or "Signal"
        return TrendAnalysis(
            direction="stable",
            rate_of_change=0.0,
            stability_score=50,
            volatility_score=0,
            observation_window=len(windowed),
            summary=f"{label} has insufficient history for trend analysis.",
        )

    signals = _compute_signals(windowed)
    label = measurement_label or "Signal"
    summary = _build_summary(label=label, signals=signals, n=len(windowed))

    return TrendAnalysis(
        direction=signals.direction,
        rate_of_change=signals.rate_of_change,
        stability_score=signals.stability_score,
        volatility_score=signals.volatility_score,
        observation_window=len(windowed),
        summary=summary,
    )

def analyze_trend_diagnostics(
    observations: Sequence[Observation],
    *,
    observation_window: int = 5,
) -> TrendDiagnostics | None:
    """Return detailed signals for internal reasoning/timeline.

    Returns None when the observation window is too small.
    """

    if observation_window <= 0:
        raise ValueError("observation_window must be > 0")
    ordered = list(observations)
    ordered.sort(key=lambda obs: (obs.timestamp, obs.id))
    windowed = ordered[-observation_window:]
    if len(windowed) < 2:
        return None
    return _compute_signals(windowed)


def _compute_signals(windowed: list[Observation]) -> TrendDiagnostics:
    values = [obs.value for obs in windowed]
    deltas = [values[i + 1] - values[i] for i in range(len(values) - 1)]

    net_change = values[-1] - values[0]
    avg_delta = net_change / max(1, len(values) - 1)

    # Start with a directional hypothesis from net change, then allow the
    # stability/monotonicity signals to override to "stable" when the direction
    # is not consistent enough for operators to trust.
    direction_hypothesis: TrendDirection
    if abs(net_change) <= 1e-9:
        direction_hypothesis = "stable"
    else:
        direction_hypothesis = "rising" if net_change > 0 else "falling"

    monotonicity = _monotonicity(deltas=deltas, direction=direction_hypothesis)
    volatility_norm = _volatility_norm(deltas=deltas, avg_delta=avg_delta)

    volatility_score = round(100 * volatility_norm)
    stability_raw = 0.65 * monotonicity + 0.35 * (1.0 - volatility_norm)
    stability_score = max(0, min(100, round(100 * stability_raw)))

    direction: TrendDirection = direction_hypothesis
    if direction_hypothesis != "stable" and stability_score < 55:
        direction = "stable"
        monotonicity = _monotonicity(deltas=deltas, direction=direction)

    return TrendDiagnostics(
        direction=direction,
        rate_of_change=avg_delta,
        monotonicity=monotonicity,
        volatility_norm=volatility_norm,
        stability_score=stability_score,
        volatility_score=volatility_score,
    )


def _monotonicity(*, deltas: list[float], direction: TrendDirection) -> float:
    """Fraction of steps aligned with the overall direction (0..1)."""

    if not deltas:
        return 1.0
    if direction == "stable":
        # Stable means changes are small; treat monotonicity as moderate unless the
        # series is perfectly flat.
        non_zero = sum(1 for d in deltas if abs(d) > 1e-12)
        return 1.0 if non_zero == 0 else 0.6

    aligned = 0
    considered = 0
    for delta in deltas:
        if abs(delta) <= 1e-12:
            continue
        considered += 1
        if (direction == "rising" and delta > 0) or (
            direction == "falling" and delta < 0
        ):
            aligned += 1
    if considered == 0:
        return 0.8
    return aligned / considered


def _volatility_norm(*, deltas: list[float], avg_delta: float) -> float:
    """Normalized volatility (0..1) from step-to-step changes.

    We treat volatility as "noise relative to typical change".
    """

    if not deltas:
        return 0.0

    mean = sum(deltas) / len(deltas)
    variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)
    std = sqrt(variance)

    denom = abs(avg_delta) + 1e-6
    ratio = std / denom
    # ratio ~0 => stable; ratio >= 1 => highly volatile
    return max(0.0, min(1.0, ratio))


def _build_summary(*, label: str, signals: TrendDiagnostics, n: int) -> str:
    direction = signals.direction
    if direction == "stable":
        if signals.volatility_score >= 60:
            return (
                f"{label} stayed within a narrow range but was noisy across the last "
                f"{n} observations."
            )
        return f"{label} remained stable across the last {n} observations."

    if signals.monotonicity >= 0.85 and signals.stability_score >= 70:
        verb = "increased" if direction == "rising" else "decreased"
        return f"{label} {verb} steadily across the last {n} observations."

    verb = "increased" if direction == "rising" else "decreased"
    qualifier = "with variability" if signals.volatility_score >= 45 else "gradually"
    return f"{label} {verb} {qualifier} across the last {n} observations."


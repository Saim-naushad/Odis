"""Trailing-window statistics (PR167 spec section 2 and section 4).

Trailing convention (documented, per the spec's requirement to state one
explicitly): for a window of length `window_seconds`, the sample set for
the row at `current timestamp` is every observation with

    current_timestamp - window_seconds < observation_timestamp <= current_timestamp

Given the pilot's fixed 10s cadence this is equivalent to, and implemented
as, the trailing `window_seconds // dt_seconds` consecutive samples ending
at and including the current sample — never centered, never including a
sample after the current one.

Six statistics per (measurement, window): mean, std (population, since a
window is its own complete population, not a sample of a larger one —
consistent with the PR166 audit's own `statistics.pstdev` convention),
min, max, slope, and delta. Slope is an ordinary-least-squares fit of
value against `elapsed_sim_seconds` within the window, in
value-units-per-second; delta is simply the current sample's value minus
the window's oldest (earliest) sample's value.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowStats:
    mean: float
    std: float
    minimum: float
    maximum: float
    slope: float
    delta: float

    def as_dict(self) -> dict[str, float]:
        return {
            "mean": self.mean,
            "std": self.std,
            "min": self.minimum,
            "max": self.maximum,
            "slope": self.slope,
            "delta": self.delta,
        }


def trailing_window(
    series: list[tuple[float, float]], current_index: int, window_samples: int
) -> list[tuple[float, float]]:
    """The `window_samples` samples ending at (and including) `current_index`.

    `series` must be sorted ascending by elapsed time. Raises `ValueError`
    if fewer than `window_samples` samples are available — callers are
    expected to only request windows already known to be complete (see
    `config.LONGEST_WINDOW_SAMPLES` and `builder.py`'s warm-up drop).
    """
    start = current_index - window_samples + 1
    if start < 0:
        raise ValueError(
            f"incomplete window: need {window_samples} samples ending at index "
            f"{current_index}, but only {current_index + 1} are available"
        )
    return series[start : current_index + 1]


def compute_window_stats(window_values: list[tuple[float, float]]) -> WindowStats:
    """Compute the six canonical statistics over one trailing window.

    `window_values` is a list of `(elapsed_sim_seconds, value)` pairs,
    ascending, already validated complete by the caller.
    """
    elapsed = [e for e, _v in window_values]
    values = [v for _e, v in window_values]

    mean = statistics.fmean(values)
    std = statistics.pstdev(values) if len(values) > 1 else 0.0
    minimum = min(values)
    maximum = max(values)
    slope = _ols_slope(elapsed, values)
    delta = values[-1] - values[0]

    return WindowStats(
        mean=mean, std=std, minimum=minimum, maximum=maximum, slope=slope, delta=delta
    )


def _ols_slope(xs: list[float], ys: list[float]) -> float:
    """Ordinary-least-squares slope of `ys` against `xs`.

    Every window this is called with has >= 3 samples at strictly
    increasing, distinct elapsed times (see `config.WINDOW_SECONDS`'s
    minimum of 30s == 3 samples), so the denominator is always positive —
    no zero-variance guard is needed for this dataset's fixed cadence.
    """
    mean_x = statistics.fmean(xs)
    mean_y = statistics.fmean(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    return numerator / denominator

"""Deterministic, seed-sampled fault-onset and severity resolution.

Mirrors `operating_conditions.py`'s range-vs-resolved split: `FaultTimingRange`
and `FaultSeverityRange` carry *sampling policy* (never sampled values) on
`ScenarioRunSpec`; `resolve_fault_start`/`resolve_fault_severity` draw from an
injected `random.Random` isolated from every other RNG stream in this package
(`run_template.resolve_run_config` constructs it from
`f"{seed}:fault_variation"`, distinct from the `operating_conditions` and
`sensor_noise` streams). When a field's fixed scalar is used instead of a
range, the corresponding resolve function returns it unchanged and never
touches `rng` — so existing fixed-value specs draw nothing from this stream
and remain exactly as reproducible as before this module existed.

`ScenarioRunSpec.__post_init__` enforces that exactly one of (fixed, range)
is set per field before either resolve function ever runs — these functions
assume that invariant rather than re-checking it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FaultTimingRange:
    """A discrete sampling grid for `fault_start_sim_seconds`.

    Valid grid values are `minimum_seconds, minimum_seconds + step_seconds,
    ...` up to and including `maximum_seconds` where the step divides evenly
    — never an arbitrary continuous draw, so a sampled fault start always
    lands on the cadence the dataset designer configured (useful for
    interpretable detection-latency calculations downstream). See
    `grid_values`.
    """

    minimum_seconds: float
    maximum_seconds: float
    step_seconds: float

    def __post_init__(self) -> None:
        if self.minimum_seconds < 0.0:
            raise ValueError("minimum_seconds must be non-negative")
        if self.step_seconds <= 0.0:
            raise ValueError("step_seconds must be positive")
        if self.maximum_seconds < self.minimum_seconds:
            raise ValueError("maximum_seconds must be >= minimum_seconds")

    def grid_values(self) -> tuple[float, ...]:
        """Every valid discrete start value, ascending.

        Always non-empty: `minimum_seconds` itself is always a valid grid
        value given `__post_init__`'s bounds. The last value is always
        `<= maximum_seconds` — a step that doesn't divide the range evenly
        simply stops short of `maximum_seconds` rather than overshooting it.
        """
        span = self.maximum_seconds - self.minimum_seconds
        step_count = int(span / self.step_seconds)
        return tuple(
            round(self.minimum_seconds + index * self.step_seconds, 6)
            for index in range(step_count + 1)
        )

    def to_json_dict(self) -> dict[str, float]:
        return {
            "minimum_seconds": self.minimum_seconds,
            "maximum_seconds": self.maximum_seconds,
            "step_seconds": self.step_seconds,
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> FaultTimingRange:
        return cls(
            minimum_seconds=float(data["minimum_seconds"]),
            maximum_seconds=float(data["maximum_seconds"]),
            step_seconds=float(data["step_seconds"]),
        )


@dataclass(frozen=True)
class FaultSeverityRange:
    """A continuous `[minimum, maximum]` sampling range for `fault_severity`.

    Unlike fault timing, severity has no discrete-grid requirement in this
    PR — drawn via `rng.uniform(minimum, maximum)`. `minimum` must be
    strictly positive: a severity of exactly `0.0` is healthy-equivalent
    while still carrying a positive fault label (the same rule
    `RunConfig`/`ScenarioRunSpec` already enforce for a fixed severity).
    """

    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if not self.minimum > 0.0:
            raise ValueError("minimum must be greater than 0.0")
        if self.maximum > 1.0:
            raise ValueError("maximum must be at most 1.0")
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")

    def to_json_dict(self) -> dict[str, float]:
        return {"minimum": self.minimum, "maximum": self.maximum}

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> FaultSeverityRange:
        return cls(minimum=float(data["minimum"]), maximum=float(data["maximum"]))


def resolve_fault_start(
    *,
    fixed: float | None,
    range_: FaultTimingRange | None,
    rng: random.Random,
) -> float | None:
    """Resolve one run's `fault_start_sim_seconds`.

    `range_` takes precedence when set (callers only ever set one of the
    two — see `ScenarioRunSpec.__post_init__`); `rng.choice` over the
    discrete grid is the only randomness this function introduces. Returns
    `fixed` (possibly `None`, for a healthy run) unchanged, touching `rng`
    not at all, when `range_` is `None`.
    """
    if range_ is not None:
        return rng.choice(range_.grid_values())
    return fixed


def resolve_fault_severity(
    *,
    fixed: float | None,
    range_: FaultSeverityRange | None,
    rng: random.Random,
) -> float:
    """Resolve one run's `fault_severity`.

    Mirrors `resolve_fault_start`; `fixed=None` with `range_=None` (a
    healthy run) resolves to `0.0`, matching `RunConfig`'s default and
    `ScenarioRunSpec`'s pre-range-support behavior exactly.
    """
    if range_ is not None:
        return rng.uniform(range_.minimum, range_.maximum)
    return fixed if fixed is not None else 0.0

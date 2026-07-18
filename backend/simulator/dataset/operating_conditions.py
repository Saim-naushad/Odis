"""Resolved and range-typed operating-condition variation for dataset runs.

Two layers, per the reproducibility contract:

- `OperatingConditions` — *resolved* concrete values, stored on `RunConfig`
  and used directly by `runner.iter_samples`. No sampling happens here.
- `OperatingConditionRanges` — documented safe sampling ranges, consumed by
  `resolve_operating_conditions` (used by `run_template.resolve_run_config`)
  to draw exactly one resolved value per field from an injected
  `random.Random`. This module never touches Python's global random state.

Defaults for both layers reproduce the pre-PR163 dataset-run trajectory
exactly: `OperatingConditions()` matches `NormalOperationProfile()`'s and
`FuelCellMachine.__init__`'s own hardcoded defaults, and an empty
`sensor_noise` tuple means no noise is applied.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

# Must match the measurement names `telemetry._CORE_MEASUREMENT_SPECS`
# produces — sensor noise only makes sense on raw/core channels, not
# derived, computed telemetry (power_output, efficiency, coolant_flow).
_SUPPORTED_NOISE_MEASUREMENTS = frozenset(
    {"stack_temperature", "stack_pressure", "current", "voltage", "fuel_flow"}
)

# Matches `FuelCellMachine.__init__`'s own defaults — the baseline that
# `InitialStateVariation`'s offsets are applied to.
_HEALTHY_INITIAL_LOAD_PERCENT = 50.0
_HEALTHY_INITIAL_STACK_TEMPERATURE_CELSIUS = 65.0

# Absolute safety bounds for a directly-constructed `OperatingConditions`
# (independent of, and wider than, `OperatingConditionRanges`'s defaults —
# see that class for why the defaults sit comfortably inside these).
_MIN_LOAD_MARGIN_PERCENT = 5.0
_MAX_LOAD_MARGIN_PERCENT = 95.0
_MAX_INITIAL_LOAD_OFFSET_PERCENT = 10.0
_MAX_INITIAL_STACK_TEMPERATURE_OFFSET_CELSIUS = 10.0


@dataclass(frozen=True)
class SensorNoiseConfig:
    """Dataset-only, zero-mean Gaussian noise for one measurement channel.

    `standard_deviation` is in the measurement's existing unit (e.g. °C for
    `stack_temperature`). `clip_std_multiple`, when set, truncates each
    noise draw to `±clip_std_multiple * standard_deviation` — a documented,
    standard statistical bound against extreme outliers.
    """

    measurement_name: str
    standard_deviation: float
    clip_std_multiple: float | None = 3.0

    def __post_init__(self) -> None:
        if self.measurement_name not in _SUPPORTED_NOISE_MEASUREMENTS:
            raise ValueError(
                f"unsupported measurement for sensor noise: "
                f"{self.measurement_name!r} (supported: "
                f"{sorted(_SUPPORTED_NOISE_MEASUREMENTS)})"
            )
        if self.standard_deviation < 0.0:
            raise ValueError("standard_deviation must be non-negative")
        if self.clip_std_multiple is not None and self.clip_std_multiple <= 0.0:
            raise ValueError("clip_std_multiple must be positive when set")

    def to_json_dict(self) -> dict[str, object]:
        """Canonical serialization — reused by `dataset_spec` (spec-level
        passthrough config) and `export` (the `runs.parquet`
        `sensor_noise_json` column) so there is exactly one place that
        defines this shape.
        """
        return {
            "measurement_name": self.measurement_name,
            "standard_deviation": self.standard_deviation,
            "clip_std_multiple": self.clip_std_multiple,
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> SensorNoiseConfig:
        clip = data.get("clip_std_multiple")
        return cls(
            measurement_name=str(data["measurement_name"]),
            standard_deviation=float(data["standard_deviation"]),
            clip_std_multiple=None if clip is None else float(clip),
        )


@dataclass(frozen=True)
class InitialStateVariation:
    """Small offsets from the target asset's healthy initial state.

    Applied only to the run's `target_asset_id` (see `runner.iter_samples`)
    — background assets keep their standard initial state.
    """

    load_offset_percent: float = 0.0
    stack_temperature_offset_celsius: float = 0.0

    def __post_init__(self) -> None:
        if abs(self.load_offset_percent) > _MAX_INITIAL_LOAD_OFFSET_PERCENT:
            raise ValueError(
                f"load_offset_percent must be within "
                f"±{_MAX_INITIAL_LOAD_OFFSET_PERCENT}"
            )
        if (
            abs(self.stack_temperature_offset_celsius)
            > _MAX_INITIAL_STACK_TEMPERATURE_OFFSET_CELSIUS
        ):
            raise ValueError(
                "stack_temperature_offset_celsius must be within "
                f"±{_MAX_INITIAL_STACK_TEMPERATURE_OFFSET_CELSIUS}"
            )

    def resolved_load_percent(self) -> float:
        return _HEALTHY_INITIAL_LOAD_PERCENT + self.load_offset_percent

    def resolved_stack_temperature_celsius(self) -> float:
        return (
            _HEALTHY_INITIAL_STACK_TEMPERATURE_CELSIUS
            + self.stack_temperature_offset_celsius
        )


@dataclass(frozen=True)
class OperatingConditions:
    """Resolved, concrete operating-condition variation for one dataset run.

    Defaults match `NormalOperationProfile()`'s hardcoded values exactly, so
    `RunConfig`'s default `operating_conditions` reproduces the pre-PR163
    dataset-run trajectory.
    """

    load_baseline_percent: float = 60.0
    load_amplitude_percent: float = 15.0
    load_period_seconds: float = 300.0
    load_phase_radians: float = 0.0
    initial_state_variation: InitialStateVariation = field(
        default_factory=InitialStateVariation
    )
    sensor_noise: tuple[SensorNoiseConfig, ...] = ()

    def __post_init__(self) -> None:
        if self.load_amplitude_percent < 0.0:
            raise ValueError("load_amplitude_percent must be non-negative")
        if self.load_period_seconds <= 0.0:
            raise ValueError("load_period_seconds must be positive")
        floor = self.load_baseline_percent - self.load_amplitude_percent
        ceiling = self.load_baseline_percent + self.load_amplitude_percent
        if floor < _MIN_LOAD_MARGIN_PERCENT or ceiling > _MAX_LOAD_MARGIN_PERCENT:
            raise ValueError(
                "load_baseline_percent +/- load_amplitude_percent must stay "
                f"within [{_MIN_LOAD_MARGIN_PERCENT}, {_MAX_LOAD_MARGIN_PERCENT}] "
                f"(got [{floor}, {ceiling}])"
            )


@dataclass(frozen=True)
class OperatingConditionRanges:
    """Documented safe sampling ranges for seeded load/initial-state variation.

    Each `(low, high)` pair is drawn once via `rng.uniform(low, high)`.
    Chosen with margin inside `OperatingConditions`' own absolute bounds
    (see module constants above) so any sampled combination is always valid
    — see `resolve_operating_conditions`.
    """

    load_baseline_percent: tuple[float, float] = (50.0, 70.0)
    load_amplitude_percent: tuple[float, float] = (5.0, 18.0)
    load_period_seconds: tuple[float, float] = (180.0, 420.0)
    load_phase_radians: tuple[float, float] = (0.0, 6.283185307179586)  # [0, 2*pi)
    initial_load_offset_percent: tuple[float, float] = (-5.0, 5.0)
    initial_stack_temperature_offset_celsius: tuple[float, float] = (-3.0, 3.0)


def resolve_operating_conditions(
    ranges: OperatingConditionRanges,
    *,
    sensor_noise: tuple[SensorNoiseConfig, ...] = (),
    rng: random.Random,
) -> OperatingConditions:
    """Draw one resolved `OperatingConditions` from `ranges` using `rng`.

    Draws happen in this fixed order — load baseline, amplitude, period,
    phase, then initial load offset, then initial temperature offset — so a
    given `rng` state (i.e. a given seed) always resolves to the same
    values. `sensor_noise` is a fixed passthrough, not sampled: noise scale
    is a per-dataset design choice, not something that should vary by seed.
    Never calls `random.seed(...)` or touches module-global random state.
    """
    return OperatingConditions(
        load_baseline_percent=rng.uniform(*ranges.load_baseline_percent),
        load_amplitude_percent=rng.uniform(*ranges.load_amplitude_percent),
        load_period_seconds=rng.uniform(*ranges.load_period_seconds),
        load_phase_radians=rng.uniform(*ranges.load_phase_radians),
        initial_state_variation=InitialStateVariation(
            load_offset_percent=rng.uniform(*ranges.initial_load_offset_percent),
            stack_temperature_offset_celsius=rng.uniform(
                *ranges.initial_stack_temperature_offset_celsius
            ),
        ),
        sensor_noise=sensor_noise,
    )

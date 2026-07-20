"""Central numerical-safety policy (PR173 spec sections 1-2).

Every feature family in this package was audited for division by zero,
near-zero-denominator instability, overflow, non-finite results, and
noise amplification (see `docs/numerically-safe-features.md`'s risk
table). Only the two cross-signal ratio features
(`features.cross_signal`) divide by a live, noisy, physically-non-negative
observed measurement that can be clipped to exactly zero by
`sensor_noise.apply_sensor_noise`'s `_MIN_PHYSICAL_VALUE` floor — every
other feature (raw/diff/rate-of-change/window statistics/fixed-reference
residuals) either performs no division at all or divides only by a fixed
constant (`DT_SECONDS`, `_RATED_MAX_CURRENT_REF`) that can never be zero.
This module is nonetheless the single place *any* feature family would
route a division through, so a future feature cannot reintroduce the same
class of bug without going through the same guard.

This policy is designed to be identically reusable by a future streaming/
online inference path (spec section 5) — `safe_divide` and
`FeatureValidity` take only plain values/primitives, no batch-specific
state, so the same functions would produce the same validity status and
reason codes for one live sample as for one row of a Parquet batch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

RejectionReason = Literal[
    "near_zero_denominator",
    "non_finite_value",
    "missing_measurement",
]
"""The complete reason-code vocabulary (spec section 2's "reason codes").
`near_zero_denominator` — a ratio's denominator fell at/below its
documented physical floor. `non_finite_value` — a defensive catch-all for
a value that computed to NaN/Inf despite passing its own guard (should
never trigger given this module's own invariants; if it ever does, that
indicates a genuine bug, not an expected operating condition).
`missing_measurement` — the source telemetry needed for a feature was
absent; not currently reachable (`builder._index_and_validate_telemetry`
guarantees one observation per measurement per eligible timestamp) but
defined now so a future feature or a future streaming source that can
have real gaps has a code path already wired to it rather than needing to
invent one under pressure.
"""

FeatureRowStatus = Literal["valid", "insufficient_data"]

# --- Ratio-feature denominator floors (spec section 4) ----------------------
#
# Both floors are physically-motivated, not statistically fit: each is an
# order of magnitude below the smallest value Plant Alpha's rated/healthy
# curve ever produces at its lowest supported load, so a value at or below
# the floor reads as "sensor/startup noise dominates the true signal",
# never a plausible operating point.

MIN_ABS_CURRENT_AMPS = 1.0
"""`voltage_per_current`'s denominator floor. Plant Alpha's rated max
current is 200A (`_RATED_MAX_CURRENT_REF`); even the pilot's lowest
configured baseline load (~45% after amplitude) keeps steady-state current
well above 50A. A reading at or below 1.0A is never a real operating
point — only sensor-noise-dominated or startup/corrupted data reach it."""

MIN_ABS_FUEL_FLOW_SLPM = 0.1
"""`power_per_fuel_flow`'s denominator floor. Plant Alpha's base fuel flow
at zero load is 1.5 SLPM (`_BASE_FUEL_FLOW_REF`); a reading at or below
0.1 SLPM is more than an order of magnitude below that floor and is never
a real operating point."""


@dataclass(frozen=True)
class SafeDivisionResult:
    value: float | None
    """The computed ratio, or `None` when rejected."""
    is_valid: bool
    reason_code: RejectionReason | None
    denominator_name: str
    denominator_value: float


def safe_divide(
    numerator: float,
    denominator: float,
    *,
    min_abs_denominator: float,
    denominator_name: str,
) -> SafeDivisionResult:
    """A ratio feature's only entry point in this codebase (spec section
    2's "Safe division"): never substitutes an epsilon for the
    denominator to produce a large-but-finite value — that would silently
    manufacture a number with no physical meaning. Below `min_abs_
    denominator`, the ratio is not computed at all.
    """
    if abs(denominator) < min_abs_denominator:
        return SafeDivisionResult(
            value=None,
            is_valid=False,
            reason_code="near_zero_denominator",
            denominator_name=denominator_name,
            denominator_value=denominator,
        )
    value = numerator / denominator
    if not math.isfinite(value):
        return SafeDivisionResult(
            value=None,
            is_valid=False,
            reason_code="non_finite_value",
            denominator_name=denominator_name,
            denominator_value=denominator,
        )
    return SafeDivisionResult(
        value=value,
        is_valid=True,
        reason_code=None,
        denominator_name=denominator_name,
        denominator_value=denominator,
    )


@dataclass
class FeatureRowValidity:
    """Accumulates every feature's validity for one `(run, asset,
    timestamp)` row as it is computed, so `builder.build_feature_table`
    can decide the row's overall status once every feature family has run
    (spec section 3's `FeatureRowResult` contract)."""

    invalid_feature_names: list[str] = field(default_factory=list)
    reason_codes: list[RejectionReason] = field(default_factory=list)
    diagnostic_values: dict[str, float] = field(default_factory=dict)

    @property
    def status(self) -> FeatureRowStatus:
        return "insufficient_data" if self.invalid_feature_names else "valid"

    def record_division(self, feature_name: str, result: SafeDivisionResult) -> None:
        if result.is_valid:
            return
        self.invalid_feature_names.append(feature_name)
        assert result.reason_code is not None
        self.reason_codes.append(result.reason_code)
        self.diagnostic_values[result.denominator_name] = result.denominator_value

    def record_non_finite(self, feature_name: str, value: float) -> None:
        self.invalid_feature_names.append(feature_name)
        self.reason_codes.append("non_finite_value")
        self.diagnostic_values[feature_name] = value

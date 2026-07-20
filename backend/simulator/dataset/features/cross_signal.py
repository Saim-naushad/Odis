"""Cross-signal physically-interpretable ratio features (PR167 spec
section 5; safety policy revised by PR173 spec section 4).

Two features shipped, each computed from the current sample's raw
telemetry only (not window-aggregated):

- `voltage_per_current` = voltage / current, units V/A. An
  internal-resistance-scale quantity — roughly constant under healthy
  load variation, shifted by hydrogen starvation's added voltage droop.
  Not a duplicate of any emitted measurement. Valid operating domain:
  `current` in Plant Alpha's normal load range is tens to ~200A; below
  `safety.MIN_ABS_CURRENT_AMPS` (1.0A) the reading is sensor-noise- or
  startup-dominated, not a real operating point.
- `power_per_fuel_flow` = power_output / fuel_flow, units kW/SLPM. This is
  the *unclamped* analogue of the emitted `efficiency` channel
  (`efficiency = min(100, power/(fuel_flow * LHV) * 100)` —
  see `telemetry.derived_observations_from_values`). PR166's audit found
  `efficiency` saturated at its 100% ceiling for ~89% of feature-eligible
  samples; `power_per_fuel_flow` has no such clamp, so it retains spread
  `efficiency` loses. This is a deliberate, documented difference, not a
  reintroduction of `efficiency` under another name. Valid operating
  domain: `fuel_flow` is at least Plant Alpha's zero-load base flow of
  1.5 SLPM; below `safety.MIN_ABS_FUEL_FLOW_SLPM` (0.1 SLPM) the reading
  is sensor-noise-dominated, not a real operating point.

Both denominators are physically non-negative and, in-distribution,
always well above their floor — but sensor noise under a large enough
distribution shift can clip either to exactly zero (PR171/PR172's
`high_noise` cohort measured this directly: `fuel_flow` clips to 0.0 via
`sensor_noise.apply_sensor_noise`'s non-negative floor at low-load
moments, at a 1.90% rate). `safety.safe_divide` rejects the ratio below
its documented floor rather than dividing by a near-zero value or
substituting an epsilon — see `docs/numerically-safe-features.md` for the
full policy and the physical reasoning behind each floor's magnitude.

**Kept as safe-rejected ratios, not redesigned**: per PR173 spec section
4, a feature is not removed solely because one noisy dataset triggered
it. Both ratios remain physically meaningful across their valid domain
and are the only two features in the full 153-feature contract that
divide by a live, noisy measurement — everything else either performs no
division or divides by a fixed constant (see `residuals.py`'s reference
curves, which divide by `_RATED_MAX_CURRENT_REF`, never by an observed
value).

Two candidates were considered and deliberately **not** shipped (PR167):

- `power_error` (`power_output - voltage*current/1000`): this is exactly
  how `power_output` itself is already computed
  (`telemetry.derived_observations_from_values`), so it is a duplicate of
  an existing emitted relationship, differing from zero only by
  floating-point rounding (~1e-4 scale) — it carries no information.
- `temperature_per_current`: `stack_temperature` has a large nonzero
  additive offset even at zero load (`_BASE_TEMPERATURE_CELSIUS = 55.0`),
  so dividing it by current does not correspond to any real physical
  invariant the way `voltage_per_current` (a droop-curve slope) or
  `power_per_fuel_flow` (an efficiency ratio) do — it was rejected as
  "mathematically available but not physically meaningful."
"""

from __future__ import annotations

from backend.simulator.dataset.features.safety import (
    MIN_ABS_CURRENT_AMPS,
    MIN_ABS_FUEL_FLOW_SLPM,
    SafeDivisionResult,
    safe_divide,
)

CROSS_SIGNAL_FEATURES: tuple[str, ...] = ("voltage_per_current", "power_per_fuel_flow")


def compute_cross_signal_features(
    *, voltage: float, current: float, power_output: float, fuel_flow: float
) -> dict[str, SafeDivisionResult]:
    return {
        "voltage_per_current": safe_divide(
            voltage,
            current,
            min_abs_denominator=MIN_ABS_CURRENT_AMPS,
            denominator_name="current",
        ),
        "power_per_fuel_flow": safe_divide(
            power_output,
            fuel_flow,
            min_abs_denominator=MIN_ABS_FUEL_FLOW_SLPM,
            denominator_name="fuel_flow",
        ),
    }

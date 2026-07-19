"""Cross-signal physically-interpretable ratio features (PR167 spec section 5).

Two features shipped, each computed from the current sample's raw
telemetry only (not window-aggregated):

- `voltage_per_current` = voltage / current, units V/A. An
  internal-resistance-scale quantity — roughly constant under healthy
  load variation, shifted by hydrogen starvation's added voltage droop.
  Not a duplicate of any emitted measurement.
- `power_per_fuel_flow` = power_output / fuel_flow, units kW/SLPM. This is
  the *unclamped* analogue of the emitted `efficiency` channel
  (`efficiency = min(100, power/(fuel_flow * LHV) * 100)` —
  see `telemetry.derived_observations_from_values`). PR166's audit found
  `efficiency` saturated at its 100% ceiling for ~89% of feature-eligible
  samples; `power_per_fuel_flow` has no such clamp, so it retains spread
  `efficiency` loses. This is a deliberate, documented difference, not a
  reintroduction of `efficiency` under another name.

Both divide by a measurement (`current`, `fuel_flow`) that is physically
non-negative and, in this dataset, always well above zero (Plant Alpha
never reaches true zero load or zero fuel flow) — but the guard below is
unconditional and documented rather than assuming that data property:
a denominator with `abs(value) < _EPSILON` produces `None` (a null
feature value), never `inf`/`nan`, per the spec's "zero denominators
should produce a documented bounded/null result" requirement.

Two candidates were considered and deliberately **not** shipped:

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

_EPSILON = 1e-6

CROSS_SIGNAL_FEATURES: tuple[str, ...] = ("voltage_per_current", "power_per_fuel_flow")


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if abs(denominator) < _EPSILON:
        return None
    return numerator / denominator


def compute_cross_signal_features(
    *, voltage: float, current: float, power_output: float, fuel_flow: float
) -> dict[str, float | None]:
    return {
        "voltage_per_current": _safe_ratio(voltage, current),
        "power_per_fuel_flow": _safe_ratio(power_output, fuel_flow),
    }

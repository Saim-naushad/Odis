"""Maps normalized dataset severity onto each fault scenario's ramp endpoints.

This module deliberately stops at endpoint values — it does not construct or
tick a `Scenario` object. See `fault_effect.py` for why: the existing
`Scenario` fault classes compute their new ramp target *after* advancing
physics for the current tick (see `cooling_degradation.py` etc.), so a
target they compute only takes effect starting the *following* tick. That
one-tick delay is fine for the live simulator but is exactly the kind of
offset the dataset ground-truth contract forbids between a sample's label
and the physical effect that produced it. `fault_effect.apply_fault_effect`
uses these endpoints directly, applied at the exact progress of the current
sample, instead.
"""

from __future__ import annotations

from backend.simulator.dataset.run_config import DatasetScenario, RunConfig

# Endpoints below are each existing scenario's own current defaults (also
# what `demo_realistic` uses) — severity=1.0 reproduces that existing
# maximum effect exactly; severity=0.0 would collapse the ramp target back
# to "no effect", but `RunConfig` now rejects fault_severity=0.0 for fault
# scenarios (a zero-effect fault run would be healthy-equivalent while
# still carrying a positive fault label). Severity varies only the ramp's
# end point, never its start point or duration.
_COOLING_START_EFFICIENCY = 0.85
_COOLING_MAX_END_EFFICIENCY = 0.55

_HYDROGEN_START_FACTOR = 1.0
_HYDROGEN_MAX_END_FACTOR = 0.6

_SENSOR_START_BIAS_CELSIUS = 0.0
_SENSOR_MAX_END_BIAS_CELSIUS = 12.0


def fault_ramp_endpoints(config: RunConfig) -> tuple[float, float]:
    """Return `(start_value, end_value)` for `config`'s fault ramp.

    The instantaneous value at a given progress fraction is
    `start + (end - start) * progress` — see `fault_effect.apply_fault_effect`.
    """
    if config.scenario_name is DatasetScenario.COOLING_DEGRADATION:
        end = _COOLING_START_EFFICIENCY - config.fault_severity * (
            _COOLING_START_EFFICIENCY - _COOLING_MAX_END_EFFICIENCY
        )
        return _COOLING_START_EFFICIENCY, end
    if config.scenario_name is DatasetScenario.HYDROGEN_SUPPLY_ISSUE:
        end = _HYDROGEN_START_FACTOR - config.fault_severity * (
            _HYDROGEN_START_FACTOR - _HYDROGEN_MAX_END_FACTOR
        )
        return _HYDROGEN_START_FACTOR, end
    if config.scenario_name is DatasetScenario.SENSOR_ANOMALY:
        end = config.fault_severity * _SENSOR_MAX_END_BIAS_CELSIUS
        return _SENSOR_START_BIAS_CELSIUS, end
    msg = f"unsupported fault scenario for dataset generation: {config.scenario_name}"
    raise ValueError(msg)

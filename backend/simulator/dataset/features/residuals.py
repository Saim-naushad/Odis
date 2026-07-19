"""Physics-informed residual features (PR167 spec section 6).

A residual feature is `observed - expected_healthy(observable_context)`.
This module ships the **interface** (`ResidualSpec`, `compute_residuals`)
plus four "v0" residuals whose `expected_healthy` function is a *fixed,
documented reference curve* — never a value fit from training data, never
a fault label, and never a hidden simulator-internal variable read at
feature-computation time. Each reference function's only input is the
current sample's own observable `current` reading.

## Why a fixed reference curve, not "hidden state," and not "fitting"

The reference constants below are Plant Alpha's own rated/healthy
operating-curve constants (see `backend/simulator/machine.py`'s
`FuelCellMachine` class attributes, cited per-function below). Using them
here is analogous to a real fleet operator using a manufacturer's rated
I-V/fuel-flow curve as a healthy reference — a fixed, published constant,
not something read from a live internal control variable at inference
time (this module never touches `cooling_efficiency`, `fuel_supply_factor`,
or any other `FuelCellMachineState` field; it only ever reads the emitted,
observable `current` telemetry value plus these literals) and not
something estimated from this dataset's training split (there is no
fitting anywhere in this module — see the deferred residuals below).

**Documented limitation**: because the reference is fixed to this specific
simulated fleet's constants, a residual computed against a *different*
real or simulated fleet would need that fleet's own rated curve
substituted in — the residual *definition* (observed minus a
current-conditioned healthy reference) generalizes; these specific
literals do not.

## What is deferred

A more accurate healthy reference — e.g. one that jointly conditions on
`current` *and* `coolant_flow`, or one whose coefficients are calibrated
by regression against this dataset's own healthy (`normal_operation`)
runs — would require fitting, which per the spec must be training-split-
only and is deferred to a future PR. This module intentionally ships only
the interface and the zero-fitting v0 residuals now.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# Reference constants mirror backend.simulator.machine.FuelCellMachine's own
# class attributes (Plant Alpha's documented rated/healthy curve) — see the
# module docstring for why this is a fixed reference, not fitted or hidden
# state.
_OPEN_CIRCUIT_VOLTAGE_REF = 0.78  # FuelCellMachine._OPEN_CIRCUIT_VOLTAGE
_VOLTAGE_DROOP_COEFFICIENT_REF = 0.06  # FuelCellMachine._VOLTAGE_LOAD_COEFFICIENT
_RATED_MAX_CURRENT_REF = 200.0  # FuelCellMachine._MAX_CURRENT_AMPS
_BASE_FUEL_FLOW_REF = 1.5  # FuelCellMachine._BASE_FUEL_FLOW_SLPM
_FUEL_FLOW_LOAD_COEFFICIENT_REF = 1.0  # FuelCellMachine._FUEL_FLOW_LOAD_COEFFICIENT
_BASE_TEMPERATURE_REF = 55.0  # FuelCellMachine._BASE_TEMPERATURE_CELSIUS
# FuelCellMachine._TEMPERATURE_LOAD_COEFFICIENT
_TEMPERATURE_LOAD_COEFFICIENT_REF = 20.0
_HEALTHY_COOLING_BONUS_REF = 0.5  # (0.85-0.8)*10, healthy default cooling_efficiency
_BASE_COOLANT_FLOW_REF = 8.0  # machine._coolant_flow's base term
_COOLANT_FLOW_LOAD_COEFFICIENT_REF = 18.0  # machine._coolant_flow's load term


def _expected_healthy_voltage(current: float) -> float:
    """Healthy open-circuit-voltage-minus-load-droop curve, volts."""
    load_fraction = current / _RATED_MAX_CURRENT_REF
    return _OPEN_CIRCUIT_VOLTAGE_REF - load_fraction * _VOLTAGE_DROOP_COEFFICIENT_REF


def _expected_healthy_fuel_flow(current: float) -> float:
    """Healthy base-plus-load fuel-flow curve, SLPM."""
    load_fraction = current / _RATED_MAX_CURRENT_REF
    return _BASE_FUEL_FLOW_REF + load_fraction * _FUEL_FLOW_LOAD_COEFFICIENT_REF


def _expected_healthy_stack_temperature(current: float) -> float:
    """Healthy base-plus-load-minus-healthy-cooling-bonus curve, °C.

    Uses `current` as a proxy for load fraction — the same proxy every
    residual in this module uses. This is a simplification (the real
    machine model uses commanded load directly, not current), documented
    here rather than silently assumed: for `hydrogen_supply_issue`, current
    itself is fault-depressed, so this residual's reference shifts down
    together with the fault — it is not a clean cooling-only signal for
    that class, and is best interpreted as most diagnostic for classes
    that do not themselves affect current (`cooling_degradation`,
    `sensor_anomaly`).
    """
    load_fraction = current / _RATED_MAX_CURRENT_REF
    return (
        _BASE_TEMPERATURE_REF
        + load_fraction * _TEMPERATURE_LOAD_COEFFICIENT_REF
        - _HEALTHY_COOLING_BONUS_REF
    )


def _expected_healthy_coolant_flow(current: float) -> float:
    """Healthy base-plus-load coolant-flow curve, L/min (see the
    stack_temperature reference's docstring for the same current-as-load-
    proxy caveat)."""
    load_fraction = current / _RATED_MAX_CURRENT_REF
    return _BASE_COOLANT_FLOW_REF + load_fraction * _COOLANT_FLOW_LOAD_COEFFICIENT_REF


@dataclass(frozen=True)
class ResidualSpec:
    """One residual feature: `observed_measurement - reference_fn(current)`."""

    name: str
    observed_measurement: str
    reference_fn: Callable[[float], float]


RESIDUAL_SPECS: tuple[ResidualSpec, ...] = (
    ResidualSpec("voltage__healthy_residual", "voltage", _expected_healthy_voltage),
    ResidualSpec(
        "fuel_flow__healthy_residual", "fuel_flow", _expected_healthy_fuel_flow
    ),
    ResidualSpec(
        "stack_temperature__healthy_residual",
        "stack_temperature",
        _expected_healthy_stack_temperature,
    ),
    ResidualSpec(
        "coolant_flow__healthy_residual", "coolant_flow", _expected_healthy_coolant_flow
    ),
)


def compute_residuals(
    *, current: float, observed_by_measurement: dict[str, float]
) -> dict[str, float]:
    """Compute every `RESIDUAL_SPECS` entry from the current sample's values."""
    return {
        spec.name: observed_by_measurement[spec.observed_measurement]
        - spec.reference_fn(current)
        for spec in RESIDUAL_SPECS
    }

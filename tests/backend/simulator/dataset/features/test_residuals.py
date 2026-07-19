"""Physics-informed residual formulas (PR167 spec section 6)."""

from __future__ import annotations

import pytest

from backend.simulator.dataset.features.residuals import (
    RESIDUAL_SPECS,
    compute_residuals,
)


def test_residual_is_zero_when_observed_matches_reference_exactly() -> None:
    current = 100.0
    expected_voltage = 0.78 - (current / 200.0) * 0.06
    expected_fuel_flow = 1.5 + (current / 200.0) * 1.0
    expected_temperature = 55.0 + (current / 200.0) * 20.0 - 0.5
    expected_coolant_flow = 8.0 + (current / 200.0) * 18.0

    residuals = compute_residuals(
        current=current,
        observed_by_measurement={
            "voltage": expected_voltage,
            "fuel_flow": expected_fuel_flow,
            "stack_temperature": expected_temperature,
            "coolant_flow": expected_coolant_flow,
        },
    )

    for name in (
        "voltage__healthy_residual",
        "fuel_flow__healthy_residual",
        "stack_temperature__healthy_residual",
        "coolant_flow__healthy_residual",
    ):
        assert residuals[name] == pytest.approx(0.0, abs=1e-9)


def test_residual_is_negative_when_observed_is_below_reference() -> None:
    current = 100.0
    expected_voltage = 0.78 - (current / 200.0) * 0.06
    residuals = compute_residuals(
        current=current,
        observed_by_measurement={
            "voltage": expected_voltage - 0.05,  # a starvation-like droop
            "fuel_flow": 2.0,
            "stack_temperature": 65.0,
            "coolant_flow": 18.0,
        },
    )
    assert residuals["voltage__healthy_residual"] == pytest.approx(-0.05)


def test_residual_specs_names_are_unique_and_deterministic_order() -> None:
    names = [spec.name for spec in RESIDUAL_SPECS]
    assert len(names) == len(set(names))
    assert names == [
        "voltage__healthy_residual",
        "fuel_flow__healthy_residual",
        "stack_temperature__healthy_residual",
        "coolant_flow__healthy_residual",
    ]

"""Cross-signal ratio features, including zero-denominator behavior
(PR167 spec sections 5, 11, and 12)."""

from __future__ import annotations

from backend.simulator.dataset.features.cross_signal import (
    compute_cross_signal_features,
)


def test_ratios_computed_normally() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=100.0, power_output=0.075, fuel_flow=2.0
    )
    assert result["voltage_per_current"] == 0.75 / 100.0
    assert result["power_per_fuel_flow"] == 0.075 / 2.0


def test_zero_current_produces_null_not_infinity() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=0.0, power_output=0.075, fuel_flow=2.0
    )
    assert result["voltage_per_current"] is None
    assert result["power_per_fuel_flow"] == 0.075 / 2.0


def test_zero_fuel_flow_produces_null_not_infinity() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=100.0, power_output=0.075, fuel_flow=0.0
    )
    assert result["power_per_fuel_flow"] is None
    assert result["voltage_per_current"] == 0.75 / 100.0


def test_near_zero_denominator_below_epsilon_is_also_null() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=1e-9, power_output=0.075, fuel_flow=2.0
    )
    assert result["voltage_per_current"] is None

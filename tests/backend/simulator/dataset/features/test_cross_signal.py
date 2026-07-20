"""Cross-signal ratio features, including safe-rejection behavior below
each ratio's documented denominator floor (PR167 spec sections 5, 11, and
12; PR173 spec sections 1/4/9's numerical-safety policy)."""

from __future__ import annotations

from backend.simulator.dataset.features.cross_signal import (
    compute_cross_signal_features,
)


def test_ratios_computed_normally() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=100.0, power_output=0.075, fuel_flow=2.0
    )
    assert result["voltage_per_current"].is_valid
    assert result["voltage_per_current"].value == 0.75 / 100.0
    assert result["power_per_fuel_flow"].is_valid
    assert result["power_per_fuel_flow"].value == 0.075 / 2.0


def test_zero_current_rejected_not_infinity() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=0.0, power_output=0.075, fuel_flow=2.0
    )
    voltage_per_current = result["voltage_per_current"]
    assert not voltage_per_current.is_valid
    assert voltage_per_current.value is None
    assert voltage_per_current.reason_code == "near_zero_denominator"
    assert voltage_per_current.denominator_name == "current"
    assert result["power_per_fuel_flow"].is_valid
    assert result["power_per_fuel_flow"].value == 0.075 / 2.0


def test_zero_fuel_flow_rejected_not_infinity() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=100.0, power_output=0.075, fuel_flow=0.0
    )
    power_per_fuel_flow = result["power_per_fuel_flow"]
    assert not power_per_fuel_flow.is_valid
    assert power_per_fuel_flow.value is None
    assert power_per_fuel_flow.reason_code == "near_zero_denominator"
    assert power_per_fuel_flow.denominator_name == "fuel_flow"
    assert result["voltage_per_current"].is_valid


def test_current_below_physical_floor_rejected() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=0.5, power_output=0.075, fuel_flow=2.0
    )
    assert not result["voltage_per_current"].is_valid


def test_negative_current_near_zero_also_rejected() -> None:
    """Both directions of a near-zero denominator are rejected (spec
    section 9's "denominator below negative epsilon")."""
    result = compute_cross_signal_features(
        voltage=0.75, current=-0.5, power_output=0.075, fuel_flow=2.0
    )
    assert not result["voltage_per_current"].is_valid


def test_fuel_flow_below_physical_floor_rejected() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=100.0, power_output=0.075, fuel_flow=0.05
    )
    assert not result["power_per_fuel_flow"].is_valid


def test_denominator_just_above_floor_is_valid() -> None:
    result = compute_cross_signal_features(
        voltage=0.75, current=1.5, power_output=0.075, fuel_flow=0.2
    )
    assert result["voltage_per_current"].is_valid
    assert result["power_per_fuel_flow"].is_valid


def test_very_noisy_but_finite_inputs_stay_valid() -> None:
    result = compute_cross_signal_features(
        voltage=1.9, current=250.0, power_output=475.0, fuel_flow=45.0
    )
    assert result["voltage_per_current"].is_valid
    assert result["power_per_fuel_flow"].is_valid
    assert result["voltage_per_current"].value == 1.9 / 250.0
    assert result["power_per_fuel_flow"].value == 475.0 / 45.0

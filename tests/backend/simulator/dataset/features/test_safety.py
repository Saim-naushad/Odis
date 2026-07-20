"""Central numerical-safety policy (PR173 spec sections 2 and 9)."""

from __future__ import annotations

import math

from backend.simulator.dataset.features.safety import (
    FeatureRowValidity,
    safe_divide,
)


def test_denominator_exactly_zero_rejected() -> None:
    result = safe_divide(1.0, 0.0, min_abs_denominator=1.0, denominator_name="x")
    assert not result.is_valid
    assert result.value is None
    assert result.reason_code == "near_zero_denominator"


def test_denominator_below_positive_epsilon_rejected() -> None:
    result = safe_divide(1.0, 0.5, min_abs_denominator=1.0, denominator_name="x")
    assert not result.is_valid


def test_denominator_below_negative_epsilon_rejected() -> None:
    result = safe_divide(1.0, -0.5, min_abs_denominator=1.0, denominator_name="x")
    assert not result.is_valid


def test_safe_positive_denominator_valid() -> None:
    result = safe_divide(3.0, 1.5, min_abs_denominator=1.0, denominator_name="x")
    assert result.is_valid
    assert result.value == 2.0


def test_safe_negative_denominator_valid() -> None:
    result = safe_divide(3.0, -1.5, min_abs_denominator=1.0, denominator_name="x")
    assert result.is_valid
    assert result.value == -2.0


def test_result_never_infinite_or_nan() -> None:
    for denominator in (0.0, 1e-9, -1e-9, 0.5, -0.5):
        result = safe_divide(
            1.0, denominator, min_abs_denominator=1.0, denominator_name="x"
        )
        if result.value is not None:
            assert math.isfinite(result.value)


def test_feature_row_validity_status_transitions() -> None:
    validity = FeatureRowValidity()
    assert validity.status == "valid"

    rejected = safe_divide(
        1.0, 0.0, min_abs_denominator=1.0, denominator_name="current"
    )
    validity.record_division("voltage_per_current", rejected)
    assert validity.status == "insufficient_data"
    assert validity.invalid_feature_names == ["voltage_per_current"]
    assert validity.reason_codes == ["near_zero_denominator"]
    assert validity.diagnostic_values == {"current": 0.0}


def test_feature_row_validity_ignores_valid_divisions() -> None:
    validity = FeatureRowValidity()
    ok = safe_divide(1.0, 2.0, min_abs_denominator=1.0, denominator_name="current")
    validity.record_division("voltage_per_current", ok)
    assert validity.status == "valid"
    assert validity.invalid_feature_names == []

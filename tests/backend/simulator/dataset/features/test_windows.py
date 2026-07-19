"""Window-statistic correctness on simple, hand-computed sequences
(PR167 spec section 12, "Window correctness")."""

from __future__ import annotations

import pytest

from backend.simulator.dataset.features.raw_features import compute_raw_features
from backend.simulator.dataset.features.windows import (
    compute_window_stats,
    trailing_window,
)


def test_trailing_window_returns_exactly_the_requested_count() -> None:
    series = [(10.0, 1.0), (20.0, 2.0), (30.0, 3.0), (40.0, 4.0)]
    window = trailing_window(series, current_index=3, window_samples=3)
    assert window == [(20.0, 2.0), (30.0, 3.0), (40.0, 4.0)]


def test_trailing_window_never_includes_a_future_sample() -> None:
    series = [(10.0, 1.0), (20.0, 2.0), (30.0, 3.0)]
    window = trailing_window(series, current_index=1, window_samples=2)
    assert window == [(10.0, 1.0), (20.0, 2.0)]
    assert (30.0, 3.0) not in window


def test_trailing_window_raises_when_incomplete() -> None:
    series = [(10.0, 1.0), (20.0, 2.0)]
    with pytest.raises(ValueError, match="incomplete window"):
        trailing_window(series, current_index=1, window_samples=3)


def test_window_stats_mean_min_max() -> None:
    window = [(10.0, 1.0), (20.0, 2.0), (30.0, 3.0)]
    stats = compute_window_stats(window)
    assert stats.mean == pytest.approx(2.0)
    assert stats.minimum == pytest.approx(1.0)
    assert stats.maximum == pytest.approx(3.0)


def test_window_stats_std_population() -> None:
    # values 1,2,3 -> population variance = ((1-2)^2+(2-2)^2+(3-2)^2)/3 = 2/3
    window = [(10.0, 1.0), (20.0, 2.0), (30.0, 3.0)]
    stats = compute_window_stats(window)
    assert stats.std == pytest.approx((2.0 / 3.0) ** 0.5)


def test_window_stats_delta_is_current_minus_oldest() -> None:
    window = [(10.0, 5.0), (20.0, 7.0), (30.0, 9.0)]
    stats = compute_window_stats(window)
    assert stats.delta == pytest.approx(9.0 - 5.0)


def test_window_stats_slope_of_a_perfect_line() -> None:
    # value increases by 1.0 every 10 seconds -> slope = 0.1 per second
    window = [(10.0, 1.0), (20.0, 2.0), (30.0, 3.0), (40.0, 4.0)]
    stats = compute_window_stats(window)
    assert stats.slope == pytest.approx(0.1)


def test_window_stats_slope_of_a_flat_line_is_zero() -> None:
    window = [(10.0, 5.0), (20.0, 5.0), (30.0, 5.0)]
    stats = compute_window_stats(window)
    assert stats.slope == pytest.approx(0.0)


def test_raw_features_diff_and_rate_of_change() -> None:
    raw = compute_raw_features(current_value=12.0, previous_value=10.0)
    assert raw.value == pytest.approx(12.0)
    assert raw.diff == pytest.approx(2.0)
    assert raw.rate_of_change_per_second == pytest.approx(0.2)  # 2.0 / 10s

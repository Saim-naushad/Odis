"""Shared pure per-row feature computation (PR176 offline/online parity).

Extracted, without any formula change, from `builder.build_feature_table`'s
per-row loop body — `compute_feature_row` is the single place every
feature family (raw/diff/rate-of-change, trailing-window statistics,
cross-signal ratios, physics residuals) is assembled into one row. Both
the offline batch builder (`builder.py`, over a full run's arrays) and the
runtime `backend.simulator.inference` session (over a bounded per-asset
trailing buffer) call this same function with the same-shaped inputs, so
a feature vector computed incrementally from live telemetry is bit-for-bit
identical to the corresponding offline `features.parquet` row for the same
input sequence — see `docs/runtime-inference.md`'s parity section.

`series_by_measurement` and `index` are exactly `trailing_window`'s own
parameters: the caller supplies each measurement's ascending
`(elapsed_sim_seconds, value)` series and the position of the "current"
sample within it. The offline builder's series is a whole run's array;
the runtime session's series is a bounded ring buffer holding only the
last `config.LONGEST_WINDOW_SAMPLES` entries — `trailing_window` cannot
tell the difference, which is exactly the point.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from backend.simulator.dataset.features.config import (
    DEFAULT_MEASUREMENTS,
    DT_SECONDS,
    WINDOW_SECONDS,
)
from backend.simulator.dataset.features.cross_signal import (
    compute_cross_signal_features,
)
from backend.simulator.dataset.features.raw_features import compute_raw_features
from backend.simulator.dataset.features.residuals import compute_residuals
from backend.simulator.dataset.features.safety import FeatureRowValidity
from backend.simulator.dataset.features.windows import (
    compute_window_stats,
    trailing_window,
)


class NonFiniteFeatureError(Exception):
    def __init__(self, column: str, value: float, key: tuple[str, str, float]) -> None:
        run_id, asset_id, elapsed = key
        super().__init__(
            f"non-finite feature value for column {column!r} "
            f"(run={run_id!r} asset={asset_id!r} elapsed={elapsed}): {value!r} — "
            "this feature family has no documented rejection path, so a "
            "non-finite value here indicates a bug, not an expected "
            "operating condition (see features/safety.py)"
        )


def _check_finite(column: str, value: float, key: tuple[str, str, float]) -> None:
    if not math.isfinite(value):
        raise NonFiniteFeatureError(column, value, key)


@dataclass(frozen=True)
class FeatureRowResult:
    values: dict[str, float]
    """Feature-column-name -> value, in no particular order (callers that
    need `feature_column_order()`'s exact ordering re-key from this dict —
    it is a plain mapping, not itself an ordered row)."""
    validity: FeatureRowValidity


def compute_feature_row(
    *,
    current_values: dict[str, float],
    previous_values: dict[str, float],
    series_by_measurement: dict[str, list[tuple[float, float]]],
    index: int,
    row_key: tuple[str, str, float],
) -> FeatureRowResult:
    """Compute every feature-column value for one `(run_or_session, asset,
    elapsed_sim_seconds)` row.

    `current_values`/`previous_values` are this row's and the immediately
    prior row's raw measurement readings (one entry per
    `config.DEFAULT_MEASUREMENTS` name). `series_by_measurement[measurement]`
    must have at least `config.LONGEST_WINDOW_SAMPLES` entries ending at
    `index` — the caller (batch or streaming) is responsible for the
    warm-up gate; this function assumes every window it requests is
    already complete (see `windows.trailing_window`). `row_key` is used
    only to build a `NonFiniteFeatureError` message.
    """
    values: dict[str, float] = {}
    validity = FeatureRowValidity()

    for measurement in DEFAULT_MEASUREMENTS:
        raw = compute_raw_features(
            current_values[measurement], previous_values[measurement]
        )
        values[measurement] = raw.value
        values[f"{measurement}__diff_10s"] = raw.diff
        values[f"{measurement}__roc_per_s"] = raw.rate_of_change_per_second
        _check_finite(measurement, raw.value, row_key)
        _check_finite(f"{measurement}__diff_10s", raw.diff, row_key)
        _check_finite(
            f"{measurement}__roc_per_s", raw.rate_of_change_per_second, row_key
        )

        for window_seconds in WINDOW_SECONDS:
            window_samples = int(window_seconds / DT_SECONDS)
            window = trailing_window(
                series_by_measurement[measurement], index, window_samples
            )
            stats = compute_window_stats(window).as_dict()
            for stat_name, stat_value in stats.items():
                column = f"{measurement}__{stat_name}_{window_seconds}s"
                values[column] = stat_value
                _check_finite(column, stat_value, row_key)

    cross_signal = compute_cross_signal_features(
        voltage=current_values["voltage"],
        current=current_values["current"],
        power_output=current_values["power_output"],
        fuel_flow=current_values["fuel_flow"],
    )
    for column, result in cross_signal.items():
        if result.is_valid:
            assert result.value is not None
            values[column] = result.value
            _check_finite(column, result.value, row_key)
        else:
            validity.record_division(column, result)

    residuals = compute_residuals(
        current=current_values["current"],
        observed_by_measurement=current_values,
    )
    for column, value in residuals.items():
        values[column] = value
        _check_finite(column, value, row_key)

    return FeatureRowResult(values=values, validity=validity)

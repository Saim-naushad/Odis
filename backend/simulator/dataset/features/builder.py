"""Builds `features.parquet` + `labels.parquet` in memory (PR167).

Orchestrates one full pass: index and validate telemetry, drop warm-up
rows shorter than the longest trailing window, compute every feature
group per eligible `(run, asset, timestamp)` row, and build the matching
label rows for exactly the same eligible keys (so `features.parquet` and
`labels.parquet` are always row-aligned 1:1 by
`(simulation_run_id, asset_id, timestamp)`).

Run/asset isolation is structural, not just tested: every per-measurement
time series is keyed by `(simulation_run_id, asset_id, measurement)` and
every window/diff/slope computation reads only from that one series — see
`_index_and_validate_telemetry` and the per-series loop in
`build_feature_table`. There is no code path through which one run's or
asset's samples could reach another's window.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pyarrow as pa

from backend.simulator.dataset.audit.loader import DatasetHandle
from backend.simulator.dataset.audit.records import DatasetRecords
from backend.simulator.dataset.features.config import (
    DEFAULT_MEASUREMENTS,
    DT_SECONDS,
    LONGEST_WINDOW_SAMPLES,
    WINDOW_SECONDS,
)
from backend.simulator.dataset.features.cross_signal import (
    compute_cross_signal_features,
)
from backend.simulator.dataset.features.exclusions import assert_no_forbidden_features
from backend.simulator.dataset.features.labels import build_label_rows
from backend.simulator.dataset.features.raw_features import compute_raw_features
from backend.simulator.dataset.features.residuals import compute_residuals
from backend.simulator.dataset.features.schema import (
    build_features_schema,
    build_labels_schema,
    feature_column_order,
)
from backend.simulator.dataset.features.windows import (
    compute_window_stats,
    trailing_window,
)

TelemetrySeries = dict[tuple[str, str, str], list[tuple[float, float]]]


class DuplicateObservationError(Exception):
    def __init__(self, key: tuple[str, str, str], elapsed: float) -> None:
        run_id, asset_id, measurement = key
        super().__init__(
            f"duplicate telemetry observation for run={run_id!r} "
            f"asset={asset_id!r} measurement={measurement!r} "
            f"elapsed_sim_seconds={elapsed}"
        )


class UnitMismatchError(Exception):
    def __init__(self, measurement: str, units: set[str]) -> None:
        super().__init__(
            f"measurement {measurement!r} has inconsistent units: {sorted(units)}"
        )


class UnsupportedCadenceError(Exception):
    """The source dataset's sample interval doesn't match `config.DT_SECONDS`.

    `config.WINDOW_SECONDS`'s sample-count equivalents (3/6/12) are only
    correct at a 10s cadence — silently reusing them against a
    differently-sampled dataset would compute windows spanning the wrong
    amount of wall-clock time without any visible error. Fail loudly
    instead (this PR's window policy is fixed to the pilot's 10s cadence,
    not a generic multi-cadence framework).
    """

    def __init__(self, actual_dt_seconds: float) -> None:
        super().__init__(
            f"source dataset's dt_seconds={actual_dt_seconds} does not match "
            f"the feature pipeline's fixed cadence assumption of "
            f"{DT_SECONDS}s — this PR's window policy is not cadence-generic"
        )


class NonFiniteFeatureError(Exception):
    def __init__(self, column: str, value: float, key: tuple[str, str, float]) -> None:
        run_id, asset_id, elapsed = key
        super().__init__(
            f"non-finite feature value for column {column!r} "
            f"(run={run_id!r} asset={asset_id!r} elapsed={elapsed}): {value!r}"
        )


@dataclass(frozen=True)
class FeatureTable:
    features: pa.Table
    labels: pa.Table
    total_rows_before_warmup_drop: int
    dropped_warmup_rows: int
    eligible_rows: int
    metadata_columns: tuple[str, ...]
    feature_columns: tuple[str, ...]


def _index_and_validate_telemetry(
    telemetry_rows: list[dict[str, Any]], measurements: tuple[str, ...]
) -> TelemetrySeries:
    measurement_set = set(measurements)
    index: TelemetrySeries = defaultdict(list)
    units_by_measurement: dict[str, set[str]] = defaultdict(set)
    seen_keys: set[tuple[str, str, str, float]] = set()

    for row in telemetry_rows:
        measurement = row["measurement_type"]
        if measurement not in measurement_set:
            continue
        key = (row["simulation_run_id"], row["asset_id"], measurement)
        elapsed = row["elapsed_sim_seconds"]
        dedup_key = (*key, elapsed)
        if dedup_key in seen_keys:
            raise DuplicateObservationError(key, elapsed)
        seen_keys.add(dedup_key)
        units_by_measurement[measurement].add(row["unit"])
        index[key].append((elapsed, row["value"]))

    for measurement, units in units_by_measurement.items():
        if len(units) > 1:
            raise UnitMismatchError(measurement, units)

    for series in index.values():
        series.sort(key=lambda pair: pair[0])

    return index


def _timestamps_by_series(
    ground_truth_rows: list[dict[str, Any]],
) -> dict[tuple[str, str], list[tuple[float, datetime]]]:
    """`(run, asset) -> [(elapsed, timestamp), ...]`, ascending — ground truth
    has exactly one row per `(run, asset, elapsed)`, so this also gives the
    canonical elapsed-time ordering shared by every measurement's series."""
    by_series: dict[tuple[str, str], list[tuple[float, datetime]]] = defaultdict(list)
    for row in ground_truth_rows:
        key = (row["simulation_run_id"], row["asset_id"])
        by_series[key].append((row["elapsed_sim_seconds"], row["timestamp"]))
    for series in by_series.values():
        series.sort(key=lambda pair: pair[0])
    return by_series


def _check_finite(
    column: str, value: float | None, key: tuple[str, str, float]
) -> None:
    if value is not None and not math.isfinite(value):
        raise NonFiniteFeatureError(column, value, key)


def build_feature_table(handle: DatasetHandle, records: DatasetRecords) -> FeatureTable:
    if handle.spec.dt_seconds != DT_SECONDS:
        raise UnsupportedCadenceError(handle.spec.dt_seconds)

    dataset_id = handle.spec.dataset_id
    telemetry_index = _index_and_validate_telemetry(
        records.telemetry, DEFAULT_MEASUREMENTS
    )
    timestamps_by_series = _timestamps_by_series(records.ground_truth)

    metadata_columns = ("dataset_id", "simulation_run_id", "asset_id", "timestamp",
                         "elapsed_sim_seconds")
    feature_columns = tuple(feature_column_order())
    assert_no_forbidden_features(list(feature_columns))

    feature_rows: list[dict[str, Any]] = []
    eligible_keys: set[tuple[str, str, float]] = set()
    total_rows_before_drop = 0
    dropped_warmup_rows = 0

    for (run_id, asset_id), elapsed_timestamps in sorted(timestamps_by_series.items()):
        total_rows_before_drop += len(elapsed_timestamps)
        series_by_measurement = {
            measurement: telemetry_index[(run_id, asset_id, measurement)]
            for measurement in DEFAULT_MEASUREMENTS
        }
        n_samples = len(elapsed_timestamps)

        for index in range(n_samples):
            if index < LONGEST_WINDOW_SAMPLES - 1:
                dropped_warmup_rows += 1
                continue

            elapsed, timestamp = elapsed_timestamps[index]
            current_values = {
                measurement: series_by_measurement[measurement][index][1]
                for measurement in DEFAULT_MEASUREMENTS
            }
            previous_values = {
                measurement: series_by_measurement[measurement][index - 1][1]
                for measurement in DEFAULT_MEASUREMENTS
            }
            row_key = (run_id, asset_id, elapsed)

            row: dict[str, Any] = {
                "dataset_id": dataset_id,
                "simulation_run_id": run_id,
                "asset_id": asset_id,
                "timestamp": timestamp,
                "elapsed_sim_seconds": elapsed,
            }

            for measurement in DEFAULT_MEASUREMENTS:
                raw = compute_raw_features(
                    current_values[measurement], previous_values[measurement]
                )
                row[measurement] = raw.value
                row[f"{measurement}__diff_10s"] = raw.diff
                row[f"{measurement}__roc_per_s"] = raw.rate_of_change_per_second
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
                        row[column] = stat_value
                        _check_finite(column, stat_value, row_key)

            cross_signal = compute_cross_signal_features(
                voltage=current_values["voltage"],
                current=current_values["current"],
                power_output=current_values["power_output"],
                fuel_flow=current_values["fuel_flow"],
            )
            for column, value in cross_signal.items():
                row[column] = value
                _check_finite(column, value, row_key)

            residuals = compute_residuals(
                current=current_values["current"],
                observed_by_measurement=current_values,
            )
            for column, value in residuals.items():
                row[column] = value
                _check_finite(column, value, row_key)

            feature_rows.append(row)
            eligible_keys.add(row_key)

    features_table = pa.Table.from_pylist(feature_rows, schema=build_features_schema())

    eligible_ground_truth = [
        gt_row
        for gt_row in records.ground_truth
        if (
            gt_row["simulation_run_id"],
            gt_row["asset_id"],
            gt_row["elapsed_sim_seconds"],
        )
        in eligible_keys
    ]
    label_rows = build_label_rows(eligible_ground_truth, handle.splits)
    labels_table = pa.Table.from_pylist(
        [
            {
                "simulation_run_id": r.simulation_run_id,
                "asset_id": r.asset_id,
                "timestamp": r.timestamp,
                "split": r.split,
                "class_label": r.class_label,
                "is_anomalous": r.is_anomalous,
                "fault_severity": r.fault_severity,
            }
            for r in label_rows
        ],
        schema=build_labels_schema(),
    )

    return FeatureTable(
        features=features_table,
        labels=labels_table,
        total_rows_before_warmup_drop=total_rows_before_drop,
        dropped_warmup_rows=dropped_warmup_rows,
        eligible_rows=len(feature_rows),
        metadata_columns=metadata_columns,
        feature_columns=feature_columns,
    )

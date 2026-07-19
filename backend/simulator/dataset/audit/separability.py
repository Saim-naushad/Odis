"""Separability analysis without training a real model (PR166 spec section 7).

Deliberately simple: a direct single-threshold scan (an O(n log n) sweep
over sorted samples, not a reusable classifier abstraction — see the
module docstring instruction not to build one), a `statistics.correlation`
call for severity-vs-effect, and plain min/max/median for class-conditional
ranges. No scikit-learn, no persisted model.

Load-band control: runs are bucketed into load terciles by their own
`load_baseline_percent` (low/mid/high) so "overlap under comparable load
bands" compares fault samples only against healthy samples drawn from
similar operating conditions, not the full healthy population (which would
overstate separability if healthy runs happen to sit at a different load
band than a given fault class's runs).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any

from backend.simulator.dataset.audit.findings import Finding
from backend.simulator.dataset.audit.physical import (
    FAULT_CLASSES,
    MEASUREMENTS,
    TelemetryIndex,
    index_telemetry,
    pre_fault_window_start,
)
from backend.simulator.dataset.audit.records import DatasetRecords

_TRIVIAL_SEPARABILITY_THRESHOLD = 0.95


def load_band_edges(rows: list[dict[str, Any]]) -> tuple[float, float]:
    values = sorted(row["load_baseline_percent"] for row in rows)
    if len(values) < 3:
        midpoint = values[0] if values else 0.0
        return midpoint, midpoint
    return values[len(values) // 3], values[(2 * len(values)) // 3]


def band_for(value: float, edges: tuple[float, float]) -> str:
    low, high = edges
    if value <= low:
        return "low"
    if value >= high:
        return "high"
    return "mid"


def _best_threshold_balanced_accuracy(pairs: list[tuple[float, bool]]) -> float:
    """Best balanced accuracy over every valid split point, either direction.

    Sorts once, then sweeps split points left-to-right in O(n): at each
    point, everything already passed is the "healthy" side and everything
    remaining (including the current sample) is the "fault" side. The
    mirror-direction rule's accuracy is always `1 - balanced`, so tracking
    `max(balanced, 1 - balanced)` covers both threshold directions without a
    second pass.

    A split point is only evaluated *between* distinct values, never inside
    a run of tied values — a threshold can't separate two samples with the
    identical raw value, so scoring a split there would let stable-sort
    insertion order (not any real separation) manufacture a spuriously
    perfect accuracy whenever a measurement happens to be constant (e.g. an
    `efficiency` reading pegged at a clamp).
    """
    n_fault = sum(1 for _value, is_fault in pairs if is_fault)
    n_healthy = len(pairs) - n_fault
    if n_fault == 0 or n_healthy == 0 or len(pairs) < 2:
        return 0.5

    ordered = sorted(pairs, key=lambda pair: pair[0])
    fault_remaining = n_fault
    healthy_seen = 0
    best = 0.5
    index = 0
    total = len(ordered)
    while index < total:
        value = ordered[index][0]
        while index < total and ordered[index][0] == value:
            if ordered[index][1]:
                fault_remaining -= 1
            else:
                healthy_seen += 1
            index += 1
        if index < total:  # a distinct, higher value follows — a real boundary
            balanced = 0.5 * (fault_remaining / n_fault + healthy_seen / n_healthy)
            best = max(best, balanced, 1.0 - balanced)
    return best


def target_asset_samples(
    runs: list[dict[str, Any]],
    measurement: str,
    telemetry_index: TelemetryIndex,
    *,
    active_only: bool,
) -> list[tuple[float, str]]:
    """`(value, load_band)` pairs for each run's target asset.

    `active_only=True` restricts to the fault's active window (for fault
    runs); `active_only=False` uses every sample (for healthy runs, where
    the whole run is the "healthy" reference).
    """
    samples: list[tuple[float, str]] = []
    band_edges = load_band_edges(runs)
    for row in runs:
        band = band_for(row["load_baseline_percent"], band_edges)
        series = telemetry_index.get(
            (row["simulation_run_id"], row["target_asset_id"], measurement), []
        )
        if not active_only:
            samples.extend((value, band) for _elapsed, value in series)
            continue
        fault_start = row["fault_start_sim_seconds"]
        fault_duration = row["fault_duration_sim_seconds"]
        if fault_start is None or fault_duration is None:
            continue
        fault_end = fault_start + fault_duration
        samples.extend(
            (value, band)
            for elapsed, value in series
            if fault_start <= elapsed < fault_end
        )
    return samples


def _class_conditional_range(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "median": statistics.median(values),
    }


def compute_separability_summary(records: DatasetRecords) -> dict[str, Any]:
    telemetry_index = index_telemetry(records)
    runs_by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records.runs:
        runs_by_class[row["class_label"]].append(row)
    healthy_runs = runs_by_class.get("normal_operation", [])

    per_class: dict[str, dict[str, Any]] = {}
    severity_effect_correlation: dict[str, dict[str, float | None]] = {}
    class_conditional_ranges: dict[str, dict[str, dict[str, float]]] = {}

    for class_label in FAULT_CLASSES:
        fault_runs = runs_by_class.get(class_label, [])
        per_measurement: dict[str, Any] = {}
        correlations: dict[str, float | None] = {}
        ranges: dict[str, dict[str, float]] = {}

        for measurement in MEASUREMENTS:
            healthy_samples = target_asset_samples(
                healthy_runs, measurement, telemetry_index, active_only=False
            )
            fault_samples = target_asset_samples(
                fault_runs, measurement, telemetry_index, active_only=True
            )

            pairs_overall = [(value, False) for value, _band in healthy_samples] + [
                (value, True) for value, _band in fault_samples
            ]
            overall_accuracy = _best_threshold_balanced_accuracy(pairs_overall)

            by_band: dict[str, list[tuple[float, bool]]] = defaultdict(list)
            for value, band in healthy_samples:
                by_band[band].append((value, False))
            for value, band in fault_samples:
                by_band[band].append((value, True))
            band_accuracy = {
                band: _best_threshold_balanced_accuracy(pairs)
                for band, pairs in by_band.items()
            }

            per_measurement[measurement] = {
                "overall_balanced_accuracy": overall_accuracy,
                "balanced_accuracy_by_load_band": band_accuracy,
            }
            ranges[measurement] = _class_conditional_range(
                [value for value, _band in fault_samples]
            )

            severities = [row["fault_severity"] for row in fault_runs]
            changes: list[float | None] = []
            for row in fault_runs:
                series = telemetry_index.get(
                    (row["simulation_run_id"], row["target_asset_id"], measurement), []
                )
                fault_start = row["fault_start_sim_seconds"]
                fault_duration = row["fault_duration_sim_seconds"]
                if fault_start is None or fault_duration is None:
                    changes.append(None)
                    continue
                fault_end = fault_start + fault_duration
                pre_start = pre_fault_window_start(fault_start, fault_duration)
                pre = [v for t, v in series if pre_start <= t < fault_start]
                active = [v for t, v in series if fault_start <= t < fault_end]
                changes.append(
                    abs(statistics.median(active) - statistics.median(pre))
                    if pre and active
                    else None
                )
            paired = [
                (sev, chg)
                for sev, chg in zip(severities, changes, strict=True)
                if chg is not None
            ]
            correlations[measurement] = None
            if (
                len(paired) >= 3
                and len({sev for sev, _ in paired}) > 1
                and len({chg for _, chg in paired}) > 1
            ):
                # `statistics.correlation` still raises `StatisticsError` in
                # edge cases its own variance check doesn't catch (e.g. one
                # side effectively constant after float rounding) — a
                # measurement with no usable spread simply has no defined
                # severity/effect correlation, not an audit failure.
                try:
                    correlations[measurement] = statistics.correlation(
                        [sev for sev, _ in paired], [chg for _, chg in paired]
                    )
                except statistics.StatisticsError:
                    correlations[measurement] = None

        per_class[class_label] = per_measurement
        severity_effect_correlation[class_label] = correlations
        class_conditional_ranges[class_label] = ranges

    class_conditional_ranges["normal_operation"] = {
        measurement: _class_conditional_range(
            [
                value
                for value, _band in target_asset_samples(
                    healthy_runs, measurement, telemetry_index, active_only=False
                )
            ]
        )
        for measurement in MEASUREMENTS
    }

    return {
        "threshold_separability": per_class,
        "severity_effect_correlation": severity_effect_correlation,
        "class_conditional_ranges": class_conditional_ranges,
    }


def check_separability(summary: dict[str, Any]) -> list[Finding]:
    trivial: list[dict[str, Any]] = []
    for class_label, measurements in summary["threshold_separability"].items():
        for measurement, result in measurements.items():
            accuracy = result["overall_balanced_accuracy"]
            if accuracy >= _TRIVIAL_SEPARABILITY_THRESHOLD:
                trivial.append(
                    {
                        "class_label": class_label,
                        "measurement": measurement,
                        "balanced_accuracy": accuracy,
                    }
                )

    if not trivial:
        return []
    return [
        Finding(
            "low",
            "separability",
            f"{len(trivial)} (class, measurement) pair(s) are separable from "
            "healthy operation by a single raw-value threshold "
            f"(balanced accuracy >= {_TRIVIAL_SEPARABILITY_THRESHOLD:.0%}) — "
            "informational, not necessarily a defect: for the measurement a "
            "fault class is physically expected to move, high separability "
            "means the class is learnable; for an unrelated channel it would "
            "indicate leakage (cross-check against the physical-behavior "
            "section)",
            evidence={"examples": trivial},
        )
    ]

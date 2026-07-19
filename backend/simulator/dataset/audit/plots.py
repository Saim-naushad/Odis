"""Focused credibility plots (PR166 spec section 9).

Exactly the seven plots the spec asks for — no decorative dashboard, no
per-measurement grid of near-duplicate charts. `matplotlib` is optional
(the `dataset-analysis` extra): if it is not installed, `generate_plots`
returns an empty list and `report.py` notes plotting was skipped, rather
than failing the whole audit over a missing plotting dependency.

Every plot has a clear title, labeled/unit-bearing axes, and a deterministic
filename (`PlotResult.filename`); `report.py` pairs each with the one-line
caption that ships in `PlotResult.caption`.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from backend.simulator.dataset.audit.physical import (
    FAULT_CLASSES,
    TelemetryIndex,
    index_telemetry,
    pre_fault_window_start,
)
from backend.simulator.dataset.audit.records import DatasetRecords
from backend.simulator.dataset.audit.separability import (
    band_for,
    load_band_edges,
    target_asset_samples,
)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra
    MATPLOTLIB_AVAILABLE = False

_PRIMARY_MEASUREMENT_BY_CLASS = {
    "cooling_degradation": "stack_temperature",
    "hydrogen_supply_issue": "voltage",
    "sensor_anomaly": "stack_temperature",
}
_CLASS_COLORS = {
    "normal_operation": "tab:gray",
    "cooling_degradation": "tab:red",
    "hydrogen_supply_issue": "tab:orange",
    "sensor_anomaly": "tab:purple",
}


@dataclass(frozen=True)
class PlotResult:
    filename: str
    title: str
    caption: str


def _runs_by_class(records: DatasetRecords) -> dict[str, list[dict[str, Any]]]:
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records.runs:
        by_class[row["class_label"]].append(row)
    return by_class


def _plot_onset_aligned_trajectories(
    records: DatasetRecords, telemetry_index: TelemetryIndex, output_dir: Path
) -> PlotResult:
    runs_by_class = _runs_by_class(records)
    fig, axes = plt.subplots(1, len(FAULT_CLASSES), figsize=(13, 4), sharey=False)
    for ax, class_label in zip(axes, FAULT_CLASSES, strict=True):
        measurement = _PRIMARY_MEASUREMENT_BY_CLASS[class_label]
        values_by_offset: dict[float, list[float]] = defaultdict(list)
        for row in runs_by_class.get(class_label, []):
            fault_start = row["fault_start_sim_seconds"]
            if fault_start is None:
                continue
            series = telemetry_index.get(
                (row["simulation_run_id"], row["target_asset_id"], measurement), []
            )
            for elapsed, value in series:
                offset = elapsed - fault_start
                if -60.0 <= offset <= row["fault_duration_sim_seconds"] + 30.0:
                    values_by_offset[round(offset / 10.0) * 10.0].append(value)
        offsets = sorted(values_by_offset)
        medians = [statistics.median(values_by_offset[offset]) for offset in offsets]
        ax.plot(offsets, medians, color=_CLASS_COLORS[class_label])
        ax.axvline(0.0, color="black", linestyle="--", linewidth=0.8)
        ax.set_title(class_label)
        ax.set_xlabel("seconds since fault start")
        ax.set_ylabel(measurement)
    fig.suptitle("Onset-aligned median trajectory by fault class")
    fig.tight_layout()
    filename = "onset_aligned_trajectories.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Onset-aligned median trajectory by fault class",
        caption=(
            "Median value of each class's primary measurement "
            "(cooling_degradation: stack_temperature; hydrogen_supply_issue: "
            "voltage; sensor_anomaly: stack_temperature), aligned so 0 "
            "seconds is fault onset, across every run of that class."
        ),
    )


def _values_in_band(
    runs: list[dict[str, Any]],
    measurement: str,
    telemetry_index: TelemetryIndex,
    band_edges: tuple[float, float],
    target_band: str,
    *,
    active_only: bool,
) -> list[float]:
    """Values for `runs` restricted to the load band each run itself falls
    into (evaluated against `band_edges`, a shared reference so healthy and
    fault samples are bucketed on the same scale)."""
    return [
        value
        for row in runs
        if band_for(row["load_baseline_percent"], band_edges) == target_band
        for value, _band in target_asset_samples(
            [row], measurement, telemetry_index, active_only=active_only
        )
    ]


def _plot_healthy_vs_fault_distributions(
    records: DatasetRecords, telemetry_index: TelemetryIndex, output_dir: Path
) -> PlotResult:
    runs_by_class = _runs_by_class(records)
    healthy_runs = runs_by_class.get("normal_operation", [])
    fig, axes = plt.subplots(1, len(FAULT_CLASSES), figsize=(13, 4))
    for ax, class_label in zip(axes, FAULT_CLASSES, strict=True):
        measurement = _PRIMARY_MEASUREMENT_BY_CLASS[class_label]
        fault_runs = runs_by_class.get(class_label, [])
        band_edges = load_band_edges(fault_runs)
        fault_samples = target_asset_samples(
            fault_runs, measurement, telemetry_index, active_only=True
        )
        band_counts = Counter(band for _value, band in fault_samples)
        dominant_band = band_counts.most_common(1)[0][0] if band_counts else "mid"

        fault_values = [v for v, band in fault_samples if band == dominant_band] or [
            v for v, _band in fault_samples
        ]
        healthy_values = _values_in_band(
            healthy_runs, measurement, telemetry_index, band_edges, dominant_band,
            active_only=False,
        ) or [
            v
            for v, _band in target_asset_samples(
                healthy_runs, measurement, telemetry_index, active_only=False
            )
        ]

        ax.hist(
            healthy_values,
            bins=20,
            alpha=0.6,
            label="healthy",
            color=_CLASS_COLORS["normal_operation"],
        )
        ax.hist(
            fault_values,
            bins=20,
            alpha=0.6,
            label=class_label,
            color=_CLASS_COLORS[class_label],
        )
        ax.set_title(class_label)
        ax.set_xlabel(measurement)
        ax.set_ylabel("sample count")
        ax.legend(fontsize=8)
    fig.suptitle("Healthy vs. active-fault distributions (comparable load band)")
    fig.tight_layout()
    filename = "healthy_vs_fault_distributions.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Healthy vs. active-fault distributions (comparable load band)",
        caption=(
            "Distribution of each class's primary measurement during the "
            "active fault window vs. healthy operation, restricted to the "
            "load tercile band where most of that class's fault samples fall."
        ),
    )


def _plot_voltage_current_relationship(
    records: DatasetRecords, telemetry_index: TelemetryIndex, output_dir: Path
) -> PlotResult:
    runs_by_class = _runs_by_class(records)
    fig, ax = plt.subplots(figsize=(6, 5))
    for class_label in ("normal_operation", *FAULT_CLASSES):
        rows = runs_by_class.get(class_label, [])
        voltages: list[float] = []
        currents: list[float] = []
        for row in rows:
            run_id = row["simulation_run_id"]
            asset_id = row["target_asset_id"]
            voltage_series = dict(
                telemetry_index.get((run_id, asset_id, "voltage"), [])
            )
            current_series = dict(
                telemetry_index.get((run_id, asset_id, "current"), [])
            )
            active_only = class_label != "normal_operation"
            fault_start = row["fault_start_sim_seconds"]
            fault_duration = row["fault_duration_sim_seconds"]
            for elapsed, voltage in voltage_series.items():
                if active_only:
                    if fault_start is None or fault_duration is None:
                        continue
                    if not (fault_start <= elapsed < fault_start + fault_duration):
                        continue
                current = current_series.get(elapsed)
                if current is not None:
                    voltages.append(voltage)
                    currents.append(current)
        ax.scatter(
            currents,
            voltages,
            s=6,
            alpha=0.4,
            label=class_label,
            color=_CLASS_COLORS[class_label],
        )
    ax.set_xlabel("current (A)")
    ax.set_ylabel("voltage (V)")
    ax.set_title("Voltage-current relationship by class")
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "voltage_current_relationship.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Voltage-current relationship by class",
        caption=(
            "Target-asset voltage vs. current, healthy samples vs. each "
            "fault class's active-window samples — hydrogen_supply_issue is "
            "expected to shift this relationship; sensor_anomaly is expected "
            "not to."
        ),
    )


def _plot_severity_vs_effect(
    records: DatasetRecords, telemetry_index: TelemetryIndex, output_dir: Path
) -> PlotResult:
    runs_by_class = _runs_by_class(records)
    fig, axes = plt.subplots(1, len(FAULT_CLASSES), figsize=(13, 4))
    for ax, class_label in zip(axes, FAULT_CLASSES, strict=True):
        measurement = _PRIMARY_MEASUREMENT_BY_CLASS[class_label]
        severities: list[float] = []
        magnitudes: list[float] = []
        for row in runs_by_class.get(class_label, []):
            fault_start = row["fault_start_sim_seconds"]
            fault_duration = row["fault_duration_sim_seconds"]
            if fault_start is None or fault_duration is None:
                continue
            series = telemetry_index.get(
                (row["simulation_run_id"], row["target_asset_id"], measurement), []
            )
            fault_end = fault_start + fault_duration
            pre_start = pre_fault_window_start(fault_start, fault_duration)
            pre = [v for t, v in series if pre_start <= t < fault_start]
            active = [v for t, v in series if fault_start <= t < fault_end]
            if pre and active:
                severities.append(row["fault_severity"])
                magnitudes.append(
                    abs(statistics.median(active) - statistics.median(pre))
                )
        ax.scatter(severities, magnitudes, s=14, color=_CLASS_COLORS[class_label])
        ax.set_title(class_label)
        ax.set_xlabel("configured fault_severity")
        ax.set_ylabel(f"|median change| ({measurement})")
    fig.suptitle("Fault severity vs. observed effect magnitude")
    fig.tight_layout()
    filename = "severity_vs_effect_magnitude.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Fault severity vs. observed effect magnitude",
        caption=(
            "Each fault run's configured severity vs. the absolute median "
            "change in that class's primary measurement between pre-fault "
            "and active-fault windows."
        ),
    )


def _plot_fault_start_vs_severity(
    records: DatasetRecords, output_dir: Path
) -> PlotResult:
    runs_by_class = _runs_by_class(records)
    fig, ax = plt.subplots(figsize=(6, 5))
    for class_label in FAULT_CLASSES:
        rows = runs_by_class.get(class_label, [])
        fault_rows = [row for row in rows if row["fault_start_sim_seconds"] is not None]
        starts = [row["fault_start_sim_seconds"] for row in fault_rows]
        severities = [row["fault_severity"] for row in fault_rows]
        ax.scatter(
            starts,
            severities,
            label=class_label,
            color=_CLASS_COLORS[class_label],
            s=20,
        )
    ax.set_xlabel("fault_start_sim_seconds")
    ax.set_ylabel("fault_severity (configured maximum)")
    ax.set_title("Fault-start vs. severity coverage")
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "fault_start_vs_severity_coverage.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Fault-start vs. severity coverage",
        caption=(
            "Every fault run's sampled fault_start_sim_seconds against its "
            "sampled fault_severity, by class — shows how well the sampling "
            "grid/range is covered."
        ),
    )


def _plot_split_balance(
    handle_splits: dict[str, Any], records: DatasetRecords, output_dir: Path
) -> PlotResult:
    split_by_run_id: dict[str, str] = {}
    for split_name in ("train", "validation", "test"):
        for run_id in handle_splits.get(split_name, []):
            split_by_run_id[run_id] = split_name

    strata = sorted(
        {f"{row['class_label']}/{row['target_asset_id']}" for row in records.runs}
    )
    split_names = ("train", "validation", "test")
    counts: dict[str, list[int]] = {split_name: [] for split_name in split_names}
    for stratum in strata:
        class_label, asset_id = stratum.split("/")
        stratum_counts: dict[str, int] = defaultdict(int)
        for row in records.runs:
            if row["class_label"] == class_label and row["target_asset_id"] == asset_id:
                split_name_for_row = split_by_run_id.get(
                    row["simulation_run_id"], "unknown"
                )
                stratum_counts[split_name_for_row] += 1
        for split_name in split_names:
            counts[split_name].append(stratum_counts.get(split_name, 0))

    fig, ax = plt.subplots(figsize=(10, 5))
    bottom = [0] * len(strata)
    for split_name in split_names:
        ax.bar(strata, counts[split_name], bottom=bottom, label=split_name)
        bottom = [b + c for b, c in zip(bottom, counts[split_name], strict=True)]
    ax.set_xticks(range(len(strata)))
    ax.set_xticklabels(strata, rotation=90, fontsize=7)
    ax.set_ylabel("run count")
    ax.set_title("Class-by-target-asset split balance")
    ax.legend()
    fig.tight_layout()
    filename = "class_asset_split_balance.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Class-by-target-asset split balance",
        caption=(
            "Stacked train/validation/test run counts for every "
            "(class, target_asset_id) stratum."
        ),
    )


def _plot_sensor_noise_residuals(
    handle_spec_sensor_noise: tuple[Any, ...],
    records: DatasetRecords,
    telemetry_index: TelemetryIndex,
    output_dir: Path,
) -> PlotResult | None:
    if not handle_spec_sensor_noise:
        return None
    healthy_runs = [
        row for row in records.runs if row["class_label"] == "normal_operation"
    ]
    measurements = [config.measurement_name for config in handle_spec_sensor_noise]
    fig, axes = plt.subplots(1, len(measurements), figsize=(4 * len(measurements), 4))
    if len(measurements) == 1:
        axes = [axes]
    for ax, config in zip(axes, handle_spec_sensor_noise, strict=True):
        residuals: list[float] = []
        for row in healthy_runs:
            key = (
                row["simulation_run_id"],
                row["target_asset_id"],
                config.measurement_name,
            )
            series = telemetry_index.get(key, [])
            values = [value for _elapsed, value in series]
            residuals.extend(b - a for a, b in pairwise(values))
        ax.hist(residuals, bins=30, color="tab:blue", alpha=0.7)
        ax.axvline(
            config.standard_deviation, color="black", linestyle="--", linewidth=0.8
        )
        ax.axvline(
            -config.standard_deviation, color="black", linestyle="--", linewidth=0.8
        )
        ax.set_title(config.measurement_name)
        ax.set_xlabel("consecutive-sample difference (noise proxy)")
        ax.set_ylabel("sample count")
    fig.suptitle("Sensor-noise residual distributions on healthy runs")
    fig.tight_layout()
    filename = "sensor_noise_residuals.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Sensor-noise residual distributions on healthy runs",
        caption=(
            "Consecutive-sample differences for each noisy measurement on "
            "healthy runs, approximating the injected noise (the underlying "
            "physical trend changes slowly relative to the 10s sample "
            "cadence); dashed lines mark the configured ±1 standard deviation."
        ),
    )


def generate_plots(
    spec_sensor_noise: tuple[Any, ...],
    splits: dict[str, Any],
    records: DatasetRecords,
    output_dir: Path,
) -> list[PlotResult]:
    if not MATPLOTLIB_AVAILABLE:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    telemetry_index = index_telemetry(records)

    results = [
        _plot_onset_aligned_trajectories(records, telemetry_index, output_dir),
        _plot_healthy_vs_fault_distributions(records, telemetry_index, output_dir),
        _plot_voltage_current_relationship(records, telemetry_index, output_dir),
        _plot_severity_vs_effect(records, telemetry_index, output_dir),
        _plot_fault_start_vs_severity(records, output_dir),
        _plot_split_balance(splits, records, output_dir),
    ]
    noise_plot = _plot_sensor_noise_residuals(
        spec_sensor_noise, records, telemetry_index, output_dir
    )
    if noise_plot is not None:
        results.append(noise_plot)
    return results

"""The four required PR170 plots (spec section 9).

`matplotlib` is optional (the `dataset-analysis` extra) — mirrors
`models/plots.py` and `calibration/plots.py`: if unavailable,
`generate_plots` returns an empty list and the report notes plotting was
skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.simulator.dataset.alert_policy.experiment import (
    AlertPolicyExperimentResult,
)
from backend.simulator.dataset.alert_policy.state_machine import run_state_machine
from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.models.data import ExperimentDataset

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra
    MATPLOTLIB_AVAILABLE = False

_CLASS_COLORS = {
    "cooling_degradation": "tab:red",
    "hydrogen_supply_issue": "tab:orange",
    "sensor_anomaly": "tab:purple",
}


@dataclass(frozen=True)
class PlotResult:
    filename: str
    title: str
    caption: str


def _plot_false_alert_event_duration(
    result: AlertPolicyExperimentResult, output_dir: Path
) -> PlotResult:
    fig, ax = plt.subplots(figsize=(7, 5))
    baseline_durations = [
        e.duration_seconds
        for e in result.test_baseline.false_alerts.qualifying_episodes
    ]
    selected_durations = (
        [e.duration_seconds for e in result.test_false_alerts.episodes]
        if result.test_false_alerts
        else []
    )
    bin_edge = max([*baseline_durations, *selected_durations, 10]) + 20
    bins = list(np.arange(0, bin_edge, 10))
    ax.hist(
        baseline_durations,
        bins=bins,
        alpha=0.6,
        label="PR168 row-sequence (recomputed)",
        color="tab:red",
    )
    ax.hist(
        selected_durations,
        bins=bins,
        alpha=0.6,
        label="PR170 selected policy",
        color="tab:blue",
    )
    ax.set_xlabel("false-alert episode duration (seconds)")
    ax.set_ylabel("episode count")
    ax.set_title("False-alert episode durations (test split)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "false_alert_event_duration.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="False-alert episode duration",
        caption=(
            "Duration of every qualifying false-alert episode on the test "
            "split, PR168's recomputed row-sequence baseline vs. PR170's "
            "selected hysteresis policy."
        ),
    )


def _plot_alert_latency_by_class(
    result: AlertPolicyExperimentResult, output_dir: Path
) -> PlotResult:
    fig, ax = plt.subplots(figsize=(7, 5))
    if result.test_detection is not None:
        for class_label in FAULT_CLASSES:
            runs = [
                r
                for r in result.test_detection.run_results
                if r.fault_class == class_label
            ]
            latencies = [
                float(r.correct_class_latency_seconds)
                if r.correct_class_detected
                and r.correct_class_latency_seconds is not None
                else -20.0
                for r in runs
            ]
            y_positions = [f"{class_label}[{i}]" for i in range(len(runs))]
            ax.scatter(
                latencies,
                y_positions,
                color=_CLASS_COLORS[class_label],
                label=class_label,
                s=50,
            )
    ax.set_xlabel("correct-class latency (s); sentinel -20 = missed")
    ax.set_title("PR170 selected policy: detection latency by class (test)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "alert_latency_by_class.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Detection latency by class",
        caption=(
            "Each test fault run's correct-class detection latency under "
            "the selected hysteresis policy; a point at -20s means the run "
            "was never correct-class detected."
        ),
    )


def _plot_threshold_persistence_tradeoff(
    result: AlertPolicyExperimentResult, output_dir: Path
) -> PlotResult:
    fig, ax = plt.subplots(figsize=(7, 6))
    for candidate in result.policy_search.candidates:
        if candidate.median_correct_class_latency_seconds is None:
            continue
        color = "lightgray" if candidate.rejected else "tab:blue"
        marker = "x" if candidate.rejected else "o"
        ax.scatter(
            candidate.false_alert_events_per_healthy_hour,
            candidate.median_correct_class_latency_seconds,
            color=color,
            marker=marker,
            s=35,
            alpha=0.7,
        )
    selected = result.policy_search.selected
    selected_latency = (
        selected.median_correct_class_latency_seconds if selected else None
    )
    if selected is not None and selected_latency is not None:
        ax.scatter(
            selected.false_alert_events_per_healthy_hour,
            selected_latency,
            color="tab:red",
            marker="*",
            s=250,
            label="selected",
            zorder=5,
        )
    ax.set_xlabel("false confirmed alert events per healthy simulated hour")
    ax.set_ylabel("median correct-class detection latency (seconds)")
    ax.set_title("Threshold/persistence tradeoff (validation policy search)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "threshold_persistence_tradeoff.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Threshold/persistence tradeoff",
        caption=(
            "Every one of the 72 (entry probability, entry persistence, "
            "healthy exit probability, exit persistence) candidates tried "
            "on validation; gray x's were rejected, the red star is selected."
        ),
    )


def _plot_example_state_timelines(
    result: AlertPolicyExperimentResult, output_dir: Path, dataset: ExperimentDataset
) -> PlotResult | None:
    if result.selected_config is None:
        return None

    test_mask = dataset.split_mask("test")
    indices = np.nonzero(test_mask)[0]
    fault_runs = [
        (run_id, metadata)
        for run_id, metadata in dataset.run_metadata.items()
        if metadata.split == "test" and metadata.fault_class is not None
    ][:2]
    if not fault_runs:
        return None

    fig, axes = plt.subplots(
        len(fault_runs), 1, figsize=(9, 3.5 * len(fault_runs)), squeeze=False
    )
    state_levels = {"healthy": 0}
    for i, class_label in enumerate(FAULT_CLASSES):
        state_levels[f"pending_{class_label}"] = i + 1
        state_levels[f"confirmed_{class_label}"] = i + 1

    for ax, (run_id, metadata) in zip(axes[:, 0], fault_runs, strict=True):
        run_positions = [
            p
            for p in range(len(indices))
            if dataset.run_ids[indices[p]] == run_id
            and dataset.asset_ids[indices[p]] == metadata.target_asset_id
        ]
        run_positions.sort(key=lambda p: dataset.elapsed_sim_seconds[indices[p]])
        if not run_positions:
            continue
        elapsed = [
            float(dataset.elapsed_sim_seconds[indices[p]]) for p in run_positions
        ]
        proba = result.test_proba[run_positions]

        sm_result = run_state_machine(
            elapsed, proba, result.class_order, result.selected_config
        )
        levels = [state_levels.get(s, 0) for s in sm_result.row_states]

        ax.step(elapsed, levels, where="post", color="tab:blue")
        if metadata.fault_start_sim_seconds is not None:
            ax.axvline(
                metadata.fault_start_sim_seconds,
                color="black",
                linestyle="--",
                linewidth=0.8,
            )
        ax.set_yticks(list(state_levels.values()))
        ax.set_yticklabels(list(state_levels.keys()), fontsize=6)
        ax.set_title(f"{run_id} (true class: {metadata.fault_class})", fontsize=9)
        ax.set_xlabel("elapsed_sim_seconds")

    fig.tight_layout()
    filename = "example_state_timelines.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Example state timelines",
        caption=(
            "State-machine trace for a couple of test fault runs under the "
            "selected policy; dashed line marks fault onset."
        ),
    )


def generate_plots(
    result: AlertPolicyExperimentResult, output_dir: Path, dataset: ExperimentDataset
) -> list[PlotResult]:
    if not MATPLOTLIB_AVAILABLE:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    plots = [
        _plot_false_alert_event_duration(result, output_dir),
        _plot_alert_latency_by_class(result, output_dir),
        _plot_threshold_persistence_tradeoff(result, output_dir),
    ]
    timeline_plot = _plot_example_state_timelines(result, output_dir, dataset)
    if timeline_plot is not None:
        plots.append(timeline_plot)
    return plots

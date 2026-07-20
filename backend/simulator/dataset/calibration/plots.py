"""The four required PR169 plots (spec section 9).

`matplotlib` is optional (the `dataset-analysis` extra) — mirrors
`models/plots.py`: if unavailable, `generate_plots` returns an empty list
and the report notes plotting was skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.simulator.dataset.calibration.experiment import CalibrationExperimentResult

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra
    MATPLOTLIB_AVAILABLE = False


@dataclass(frozen=True)
class PlotResult:
    filename: str
    title: str
    caption: str


def _plot_reliability_diagram(
    result: CalibrationExperimentResult, output_dir: Path
) -> PlotResult:
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(
        [0, 1], [0, 1], color="black", linestyle="--", linewidth=0.8,
        label="perfect calibration",
    )

    curves = (
        (result.validation_calibration_metrics_before, "uncalibrated", "tab:red"),
        (
            result.validation_calibration_metrics_after,
            "calibrated (sigmoid)",
            "tab:blue",
        ),
    )
    for metrics, label, color in curves:
        confidences = [b.mean_confidence for b in metrics.confidence_bands]
        accuracies = [b.accuracy for b in metrics.confidence_bands]
        sizes = [max(20, b.row_count / 10) for b in metrics.confidence_bands]
        ax.plot(confidences, accuracies, color=color, marker="o", label=label)
        ax.scatter(confidences, accuracies, s=sizes, color=color, alpha=0.4)

    ax.set_xlabel("mean predicted confidence (bin)")
    ax.set_ylabel("accuracy (bin)")
    ax.set_title("Reliability diagram (validation)")
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "reliability_diagram.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Reliability diagram",
        caption=(
            "Mean predicted confidence vs. empirical accuracy per confidence "
            "bin, uncalibrated vs. sigmoid-calibrated, on the validation split "
            "(the same rows the calibrator was fit on — see the module "
            "docstring's caveat). Marker size is proportional to bin row count."
        ),
    )


def _plot_confidence_distribution(
    result: CalibrationExperimentResult, output_dir: Path
) -> PlotResult:
    fig, ax = plt.subplots(figsize=(7, 5))
    before = result.validation_calibration_metrics_before.confidence_distribution
    after = result.validation_calibration_metrics_after.confidence_distribution
    ax.axvline(before["mean"], color="tab:red", linestyle="--", linewidth=0.8)
    ax.axvline(after["mean"], color="tab:blue", linestyle="--", linewidth=0.8)
    labels = [
        "uncalibrated\np50", "uncalibrated\np90", "calibrated\np50", "calibrated\np90",
    ]
    ax.bar(
        labels,
        [before["p50"], before["p90"], after["p50"], after["p90"]],
        color=["tab:red", "tab:red", "tab:blue", "tab:blue"],
        alpha=0.7,
    )
    ax.set_ylabel("max predicted probability")
    ax.set_ylim(0.0, 1.0)
    ax.set_title("Confidence distribution: median and p90, before vs. after")
    fig.tight_layout()
    filename = "confidence_distribution.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Confidence distribution",
        caption=(
            "Median and 90th-percentile row-level max-class confidence, "
            "uncalibrated vs. calibrated, on the validation split — sigmoid "
            "calibration visibly compresses confidence toward the extremes "
            "less often being falsely overconfident at moderate scores."
        ),
    )


def _plot_coverage_accuracy_tradeoff(
    result: CalibrationExperimentResult, output_dir: Path
) -> PlotResult:
    fig, ax1 = plt.subplots(figsize=(7, 5))
    thresholds = [c.confidence_threshold for c in result.validation_coverage_grid]
    coverage = [c.coverage for c in result.validation_coverage_grid]
    balanced_accuracy = [
        c.selective_balanced_accuracy for c in result.validation_coverage_grid
    ]

    ax1.plot(thresholds, coverage, color="tab:blue", marker="o", label="coverage")
    ax1.set_xlabel("confidence threshold")
    ax1.set_ylabel("coverage", color="tab:blue")
    ax1.set_ylim(0.0, 1.05)

    ax2 = ax1.twinx()
    ax2.plot(
        thresholds, balanced_accuracy, color="tab:orange", marker="s",
        label="selective balanced accuracy",
    )
    ax2.set_ylabel("selective balanced accuracy", color="tab:orange")
    ax2.set_ylim(0.0, 1.05)

    ax1.axvline(
        result.selected_confidence_threshold,
        color="black",
        linestyle="--",
        linewidth=0.8,
    )
    ax1.set_title("Coverage vs. selective accuracy by confidence threshold")
    fig.tight_layout()
    filename = "coverage_accuracy_tradeoff.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Coverage vs. accuracy tradeoff",
        caption=(
            "Row-level coverage and selective (covered-only) balanced "
            "accuracy across the validation confidence-threshold grid; "
            "dashed line marks the selected threshold."
        ),
    )


def _plot_false_alarm_latency_tradeoff(
    result: CalibrationExperimentResult, output_dir: Path
) -> PlotResult:
    fig, ax = plt.subplots(figsize=(7, 6))
    for candidate in result.policy_search.candidates:
        if candidate.median_latency_seconds is None:
            continue
        color = "lightgray" if candidate.rejected else "tab:blue"
        marker = "x" if candidate.rejected else "o"
        ax.scatter(
            candidate.false_alarms_per_healthy_hour,
            candidate.median_latency_seconds,
            color=color,
            marker=marker,
            s=40,
        )
    selected = result.policy_search.selected
    if selected.median_latency_seconds is not None:
        ax.scatter(
            selected.false_alarms_per_healthy_hour,
            selected.median_latency_seconds,
            color="tab:red",
            marker="*",
            s=250,
            label="selected",
            zorder=5,
        )
    ax.set_xlabel("false alarms per healthy simulated hour")
    ax.set_ylabel("median detection latency (seconds)")
    ax.set_title("False-alarm rate vs. detection latency (validation policy search)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "false_alarm_latency_tradeoff.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="False-alarm/latency tradeoff",
        caption=(
            "Every (confidence threshold, persistence count) candidate tried "
            "on validation; gray x's were rejected for exceeding the "
            "missed-run cap, the red star is the selected policy."
        ),
    )


def generate_plots(
    result: CalibrationExperimentResult, output_dir: Path
) -> list[PlotResult]:
    if not MATPLOTLIB_AVAILABLE:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    return [
        _plot_reliability_diagram(result, output_dir),
        _plot_confidence_distribution(result, output_dir),
        _plot_coverage_accuracy_tradeoff(result, output_dir),
        _plot_false_alarm_latency_tradeoff(result, output_dir),
    ]

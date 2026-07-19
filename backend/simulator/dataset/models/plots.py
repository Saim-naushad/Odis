"""The four required plots (PR168 spec section 11).

`matplotlib` is optional (the `dataset-analysis` extra) — mirrors
`audit/plots.py`: if unavailable, `generate_plots` returns an empty list
and `report.py` notes plotting was skipped rather than failing the run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend.simulator.dataset.models.config import (
    DETECTION_LATENCY_THRESHOLDS_SECONDS,
    FAULT_CLASSES,
    FEATURE_GROUP_NAMES,
)
from backend.simulator.dataset.models.detection import RunDetectionResult
from backend.simulator.dataset.models.experiment import ExperimentResult
from backend.simulator.dataset.models.search import (
    HISTOGRAM_GRADIENT_BOOSTING,
    LOGISTIC_REGRESSION,
)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the extra
    MATPLOTLIB_AVAILABLE = False

_MODEL_LABELS = {
    LOGISTIC_REGRESSION: "logistic regression",
    HISTOGRAM_GRADIENT_BOOSTING: "histogram gradient boosting",
}
_MODEL_COLORS = {
    LOGISTIC_REGRESSION: "tab:blue",
    HISTOGRAM_GRADIENT_BOOSTING: "tab:orange",
}
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


def _plot_confusion_matrix(result: ExperimentResult, output_dir: Path) -> PlotResult:
    cm = result.test_metrics.confusion_matrix
    labels = result.test_metrics.class_order
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("Test confusion matrix (raw row counts)")
    for i, row in enumerate(cm):
        for j, value in enumerate(row):
            ax.text(j, i, str(value), ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    filename = "confusion_matrix.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Test confusion matrix",
        caption=(
            f"Selected pipeline ({result.ablation.selected.model_type}, feature "
            f"set {result.ablation.selected.feature_group}) on the untouched test "
            "split, raw row counts."
        ),
    )


def _plot_feature_ablation(result: ExperimentResult, output_dir: Path) -> PlotResult:
    fig, ax = plt.subplots(figsize=(7, 5))
    x = range(len(FEATURE_GROUP_NAMES))
    width = 0.35
    model_offsets = (
        (-width / 2, LOGISTIC_REGRESSION),
        (width / 2, HISTOGRAM_GRADIENT_BOOSTING),
    )
    for offset, model_type in model_offsets:
        accuracies = [
            result.ablation.best_per_group_and_model[
                (group, model_type)
            ].validation_balanced_accuracy
            for group in FEATURE_GROUP_NAMES
        ]
        ax.bar(
            [xi + offset for xi in x],
            accuracies,
            width=width,
            label=_MODEL_LABELS[model_type],
            color=_MODEL_COLORS[model_type],
        )
    ax.set_xticks(list(x))
    ax.set_xticklabels(FEATURE_GROUP_NAMES)
    ax.set_xlabel("feature set (A: raw, B: +temporal, C: +cross-signal, D: +residuals)")
    ax.set_ylabel("validation balanced accuracy")
    ax.set_title("Feature-set ablation (best hyperparameters per cell)")
    ax.legend()
    ax.set_ylim(0.0, 1.0)
    fig.tight_layout()
    filename = "feature_ablation.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Feature-set ablation",
        caption=(
            "Best validation balanced accuracy per (model, feature-set) cell — "
            "the only comparison used to answer whether temporal, cross-signal, "
            "and physics-residual features help."
        ),
    )


def _plot_severity_recall(result: ExperimentResult, output_dir: Path) -> PlotResult:
    fig, axes = plt.subplots(1, len(FAULT_CLASSES), figsize=(13, 4), sharey=True)
    band_order = ("mild", "moderate", "severe")
    for ax, class_label in zip(axes, FAULT_CLASSES, strict=True):
        groups = {g.group: g for g in result.test_severity_recall[class_label]}
        bands = [b for b in band_order if b in groups]
        recalls = [groups[b].recall for b in bands]
        colors = [
            _CLASS_COLORS[class_label] if not groups[b].small_sample else "lightgray"
            for b in bands
        ]
        ax.bar(bands, recalls, color=colors)
        for i, b in enumerate(bands):
            ax.text(
                i,
                recalls[i] + 0.02,
                f"n={groups[b].run_count} runs",
                ha="center",
                fontsize=7,
            )
        ax.set_title(class_label)
        ax.set_ylim(0.0, 1.1)
        ax.set_ylabel("recall")
    fig.suptitle("Test recall by configured-severity band (gray = < 3 runs)")
    fig.tight_layout()
    filename = "severity_recall.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Recall by severity band",
        caption=(
            "Per-class recall grouped by each run's configured maximum "
            "severity; bars are grayed out when fewer than 3 test runs back "
            "the estimate."
        ),
    )


def _plot_detection_latency(result: ExperimentResult, output_dir: Path) -> PlotResult:
    fig, ax = plt.subplots(figsize=(7, 5))
    for class_label in FAULT_CLASSES:
        runs = [
            r for r in result.test_detection.run_results if r.fault_class == class_label
        ]
        y_positions = range(len(runs))

        def _latency_or_sentinel(r: RunDetectionResult) -> float:
            if r.detected and r.latency_seconds is not None:
                return float(r.latency_seconds)
            return -10.0

        latencies = [_latency_or_sentinel(r) for r in runs]
        ax.scatter(
            latencies,
            [f"{class_label}[{i}]" for i in y_positions],
            color=_CLASS_COLORS[class_label],
            label=class_label,
            s=40,
        )
    for threshold in DETECTION_LATENCY_THRESHOLDS_SECONDS:
        ax.axvline(threshold, color="black", linestyle="--", linewidth=0.7)
    ax.set_xlabel("detection latency (seconds); sentinel -10 = missed run")
    ax.set_title("Per-run detection latency (test split)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "detection_latency.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Detection latency per fault run",
        caption=(
            "Each test fault run's detection latency under the selected "
            f"{result.persistence_policy.selected_persistence_samples}-consecutive-"
            "sample policy; dashed lines mark the 30/60/120s thresholds; a "
            "point at -10s means the run was never detected."
        ),
    )


def generate_plots(result: ExperimentResult, output_dir: Path) -> list[PlotResult]:
    if not MATPLOTLIB_AVAILABLE:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    return [
        _plot_confusion_matrix(result, output_dir),
        _plot_feature_ablation(result, output_dir),
        _plot_severity_recall(result, output_dir),
        _plot_detection_latency(result, output_dir),
    ]

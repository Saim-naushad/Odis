"""The five PR171 plots (spec section 13). `matplotlib` is optional (the
`dataset-analysis` extra) — mirrors every other `plots.py` in this
package: unavailable means `generate_plots` returns an empty list.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.simulator.dataset.ood.alert_metrics import AlertEvaluationResult
from backend.simulator.dataset.ood.comparison import GeneralizationComparison
from backend.simulator.dataset.ood.diagnosis_metrics import RowDiagnosisResult
from backend.simulator.dataset.ood.error_analysis import RepresentativeCase
from backend.simulator.dataset.ood.feature_shift import FeatureShiftReport

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


def _plot_confusion_matrix(
    ood_diagnosis: RowDiagnosisResult, output_dir: Path
) -> PlotResult:
    metrics = ood_diagnosis.multiclass_metrics
    cm = np.array(metrics.confusion_matrix)
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(metrics.class_order)))
    ax.set_yticks(range(len(metrics.class_order)))
    ax.set_xticklabels(metrics.class_order, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(metrics.class_order, fontsize=8)
    ax.set_xlabel("predicted")
    ax.set_ylabel("true")
    ax.set_title("OOD confusion matrix (frozen pipeline)")
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    filename = "ood_confusion_matrix.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="OOD confusion matrix",
        caption=(
            "Row-level confusion matrix of the frozen PR168 pipeline on the "
            "OOD v1 cohort."
        ),
    )


def _plot_id_vs_ood_metrics(
    comparison: GeneralizationComparison, output_dir: Path
) -> PlotResult:
    labels = ["balanced\naccuracy", "macro F1", "healthy\nFPR"]
    deltas = [
        comparison.balanced_accuracy,
        comparison.macro_f1,
        comparison.healthy_false_positive_rate,
    ]
    id_values = [d.id_value or 0.0 for d in deltas]
    ood_values = [d.ood_value or 0.0 for d in deltas]
    x = np.arange(len(labels))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(x - width / 2, id_values, width, label="ID (pilot test)", color="tab:blue")
    ax.bar(x + width / 2, ood_values, width, label="OOD v1", color="tab:red")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1.0)
    ax.set_title("ID vs. OOD row-level metrics")
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "id_vs_ood_metrics.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="ID vs. OOD metrics",
        caption=(
            "Balanced accuracy, macro F1, and healthy-row false-positive "
            "rate, ID vs. OOD."
        ),
    )


def _plot_feature_shift_rankings(
    feature_shift: FeatureShiftReport, output_dir: Path
) -> PlotResult:
    top = feature_shift.ranked()[:15]
    names = [e.name for e in top][::-1]
    values = [e.standardized_mean_difference for e in top][::-1]
    fig, ax = plt.subplots(figsize=(8, 6))
    colors = ["tab:red" if v >= 0 else "tab:blue" for v in values]
    ax.barh(names, values, color=colors)
    ax.set_xlabel("standardized mean difference (OOD - train)")
    ax.set_title("Most-shifted features (top 15 by |SMD|)")
    ax.tick_params(axis="y", labelsize=7)
    fig.tight_layout()
    filename = "feature_shift_rankings.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Feature shift rankings",
        caption=(
            "Top 15 features by |standardized mean difference| between the "
            "pilot training split and OOD v1."
        ),
    )


def _plot_alert_latency_comparison(
    id_alerts: AlertEvaluationResult,
    ood_alerts: AlertEvaluationResult,
    output_dir: Path,
) -> PlotResult:
    id_latencies = id_alerts.detection.correct_class_latencies
    ood_latencies = ood_alerts.detection.correct_class_latencies
    fig, ax = plt.subplots(figsize=(7, 5))
    max_latency = max([*id_latencies, *ood_latencies, 10.0])
    bins = list(np.arange(0, max_latency + 60, 30))
    ax.hist(
        id_latencies, bins=bins, alpha=0.6, label="ID (pilot test)", color="tab:blue"
    )
    ax.hist(ood_latencies, bins=bins, alpha=0.6, label="OOD v1", color="tab:red")
    ax.set_xlabel("correct-class detection latency (s)")
    ax.set_ylabel("run count")
    ax.set_title("Detection latency, ID vs. OOD")
    ax.legend(fontsize=8)
    fig.tight_layout()
    filename = "alert_latency_comparison.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Alert latency comparison",
        caption=(
            "Correct-class detection latency distribution under the frozen "
            "alert policy, ID vs. OOD."
        ),
    )


def _plot_representative_timelines(
    cases: list[RepresentativeCase], output_dir: Path
) -> PlotResult | None:
    plotted = [c for c in cases if c.timeline]
    if not plotted:
        return None
    fig, axes = plt.subplots(
        len(plotted), 1, figsize=(9, 3.0 * len(plotted)), squeeze=False
    )
    for ax, case in zip(axes[:, 0], plotted, strict=True):
        elapsed = [row.elapsed_sim_seconds for row in case.timeline]
        is_correct = [
            1 if row.predicted_label == row.true_label else 0 for row in case.timeline
        ]
        ax.step(elapsed, is_correct, where="post", color="tab:blue")
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["mismatch", "match"], fontsize=7)
        ax.set_title(
            f"{case.category}: {case.simulation_run_id}", fontsize=9
        )
        ax.set_xlabel("elapsed_sim_seconds", fontsize=8)
    fig.tight_layout()
    filename = "representative_run_timelines.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Representative run timelines",
        caption=(
            "Predicted-vs-true-label match over time for each selected "
            "representative OOD run."
        ),
    )


def generate_plots(
    *,
    ood_diagnosis: RowDiagnosisResult,
    comparison: GeneralizationComparison,
    feature_shift: FeatureShiftReport,
    id_alerts: AlertEvaluationResult,
    ood_alerts: AlertEvaluationResult,
    representative_cases: list[RepresentativeCase],
    output_dir: Path,
) -> list[PlotResult]:
    if not MATPLOTLIB_AVAILABLE:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    plots = [
        _plot_confusion_matrix(ood_diagnosis, output_dir),
        _plot_id_vs_ood_metrics(comparison, output_dir),
        _plot_feature_shift_rankings(feature_shift, output_dir),
        _plot_alert_latency_comparison(id_alerts, ood_alerts, output_dir),
    ]
    timeline_plot = _plot_representative_timelines(representative_cases, output_dir)
    if timeline_plot is not None:
        plots.append(timeline_plot)
    return plots

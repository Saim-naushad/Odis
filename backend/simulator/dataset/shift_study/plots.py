"""The five PR172 plots (spec section 12). `matplotlib` is optional (the
`dataset-analysis` extra) — mirrors every other `plots.py` in this
package: unavailable means `generate_plots` returns an empty list.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.simulator.dataset.shift_study.cohort_loading import CohortData
from backend.simulator.dataset.shift_study.rankings import ShiftDamage

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


def _plot_metric_degradation_by_shift(
    damages: dict[str, ShiftDamage], output_dir: Path
) -> PlotResult:
    names = sorted(damages, key=lambda n: (-damages[n].balanced_accuracy_drop, n))
    values = [damages[n].balanced_accuracy_drop for n in names]
    tier_colors = {
        "minor": "tab:green",
        "moderate": "tab:orange",
        "major": "tab:red",
        "catastrophic": "darkred",
    }
    colors = [
        tier_colors[damages[n].tier]
        for n in names
    ]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(names, values, color=colors)
    ax.set_ylabel("balanced-accuracy drop from ID")
    ax.set_title("Balanced-accuracy degradation by shift")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    filename = "metric_degradation_by_shift.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Metric degradation by shift",
        caption=(
            "Balanced-accuracy drop from the ID pilot test split for each "
            "cohort; color = severity tier."
        ),
    )


def _plot_false_alerts_by_shift(
    damages: dict[str, ShiftDamage], output_dir: Path
) -> PlotResult:
    names = sorted(
        damages, key=lambda n: (-damages[n].false_alert_rate_per_healthy_hour, n)
    )
    values = [damages[n].false_alert_rate_per_healthy_hour for n in names]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(names, values, color="tab:red")
    ax.set_ylabel("false confirmed alert events / healthy hour")
    ax.set_title("False-alert rate by shift")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    filename = "false_alerts_by_shift.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="False alerts by shift",
        caption="False confirmed alert events per healthy simulated hour, per cohort.",
    )


def _plot_per_class_recall_by_shift(
    cohorts: dict[str, CohortData], fault_classes: tuple[str, ...], output_dir: Path
) -> PlotResult:
    import numpy as np

    names = sorted(cohorts)
    x = np.arange(len(fault_classes))
    width = 0.8 / max(len(names), 1)
    fig, ax = plt.subplots(figsize=(8, 5))
    for i, name in enumerate(names):
        per_class = cohorts[name].ood_diagnosis["multiclass_metrics"]["per_class"]
        recalls = [per_class[cls]["recall"] for cls in fault_classes]
        ax.bar(x + i * width, recalls, width, label=name)
    ax.set_xticks(x + width * (len(names) - 1) / 2)
    ax.set_xticklabels(fault_classes, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("recall")
    ax.set_ylim(0, 1.0)
    ax.set_title("Per-class recall by shift")
    ax.legend(fontsize=7)
    fig.tight_layout()
    filename = "per_class_recall_by_shift.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Per-class recall by shift",
        caption="Row-level recall for each fault class, one bar group per cohort.",
    )


def _plot_feature_shift_by_cohort(
    cohorts: dict[str, CohortData], output_dir: Path
) -> PlotResult:
    names = sorted(cohorts)
    top_smd = []
    for name in names:
        top = cohorts[name].feature_shift.get("top_shifted_overall", [])
        top_smd.append(abs(top[0]["standardized_mean_difference"]) if top else 0.0)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(names, top_smd, color="tab:purple")
    ax.set_ylabel("|standardized mean difference| (worst feature)")
    ax.set_title("Worst per-cohort feature shift")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    filename = "feature_shift_by_cohort.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Feature shift by cohort",
        caption="Magnitude of the single most-shifted feature (by |SMD|), per cohort.",
    )


def _plot_representative_timelines(
    study_cases: dict[str, list[dict[str, Any]]], output_dir: Path
) -> PlotResult | None:
    panels: list[tuple[str, dict[str, Any]]] = []
    for cohort_name, cases in study_cases.items():
        easy = next(
            (c for c in cases if c["category"] == "successful_easy_fault"), None
        )
        if easy is not None and easy["timeline"]:
            panels.append((cohort_name, easy))
    if not panels:
        return None

    fig, axes = plt.subplots(
        len(panels), 1, figsize=(9, 2.8 * len(panels)), squeeze=False
    )
    for ax, (cohort_name, case) in zip(axes[:, 0], panels, strict=True):
        elapsed = [row["elapsed_sim_seconds"] for row in case["timeline"]]
        is_correct = [
            1 if row["predicted_label"] == row["true_label"] else 0
            for row in case["timeline"]
        ]
        ax.step(elapsed, is_correct, where="post", color="tab:blue")
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["mismatch", "match"], fontsize=7)
        ax.set_title(f"{cohort_name}: {case['simulation_run_id']}", fontsize=9)
        ax.set_xlabel("elapsed_sim_seconds", fontsize=8)
    fig.tight_layout()
    filename = "representative_shift_timelines.png"
    fig.savefig(output_dir / filename, dpi=120)
    plt.close(fig)
    return PlotResult(
        filename=filename,
        title="Representative shift timelines",
        caption=(
            "Predicted-vs-true-label match over time for one representative "
            "successful-detection run per cohort."
        ),
    )


def generate_plots(
    *,
    damages: dict[str, ShiftDamage],
    cohorts: dict[str, CohortData],
    fault_classes: tuple[str, ...],
    study_cases: dict[str, list[dict[str, Any]]],
    output_dir: Path,
) -> list[PlotResult]:
    if not MATPLOTLIB_AVAILABLE or not damages:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    plots = [
        _plot_metric_degradation_by_shift(damages, output_dir),
        _plot_false_alerts_by_shift(damages, output_dir),
        _plot_per_class_recall_by_shift(cohorts, fault_classes, output_dir),
        _plot_feature_shift_by_cohort(cohorts, output_dir),
    ]
    timeline_plot = _plot_representative_timelines(study_cases, output_dir)
    if timeline_plot is not None:
        plots.append(timeline_plot)
    return plots

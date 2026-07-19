"""`experiment_summary.json` + `evaluation_report.md` construction (PR168
spec section 11).

Mirrors `features/manifest.py` and `audit/report.py`'s split: this module
only ever reads from an already-computed `ExperimentResult` — no model
fitting, no filesystem writes (those are `generate.py`'s job).
"""

from __future__ import annotations

from typing import Any

from backend.simulator.dataset.models.config import (
    FAULT_CLASSES,
    FEATURE_GROUP_NAMES,
    MODEL_SCHEMA_VERSION,
)
from backend.simulator.dataset.models.data import ExperimentDataset
from backend.simulator.dataset.models.experiment import ExperimentResult
from backend.simulator.dataset.models.feature_groups import FEATURE_GROUP_DESCRIPTIONS
from backend.simulator.dataset.models.plots import PlotResult
from backend.simulator.dataset.models.runtime_metrics import RuntimeMetrics
from backend.simulator.dataset.models.search import (
    HISTOGRAM_GRADIENT_BOOSTING,
    LOGISTIC_REGRESSION,
)


def build_validation_metrics_json(result: ExperimentResult) -> dict[str, Any]:
    return {
        "selected_configuration": result.ablation.selected.to_json_dict(),
        "metrics": result.validation_metrics.to_json_dict(),
        "persistence_policy": result.persistence_policy.to_json_dict(),
        "reference_baseline_balanced_accuracy": (
            result.reference_baseline.validation_balanced_accuracy
        ),
    }


def build_test_metrics_json(
    result: ExperimentResult, runtime: RuntimeMetrics
) -> dict[str, Any]:
    return {
        "multiclass": result.test_metrics.to_json_dict(),
        "operational": {
            "false_positive_rate_healthy": result.test_false_positive_rate_healthy,
            "detection": result.test_detection.to_json_dict(),
            "severity_band_recall": {
                cls: [g.to_json_dict() for g in groups]
                for cls, groups in result.test_severity_recall.items()
            },
            "ramp_vs_post_ramp_recall": {
                cls: [g.to_json_dict() for g in groups]
                for cls, groups in result.test_ramp_recall.items()
            },
        },
        "runtime": runtime.to_json_dict(),
        "reference_baseline_balanced_accuracy": (
            result.reference_baseline.test_balanced_accuracy
        ),
        "bootstrap_balanced_accuracy_ci": result.bootstrap_ci,
    }


def build_experiment_summary(
    *,
    dataset: ExperimentDataset,
    result: ExperimentResult,
    runtime: RuntimeMetrics,
    plots: list[PlotResult],
    generation_command: str,
) -> dict[str, Any]:
    return {
        "model_schema_version": MODEL_SCHEMA_VERSION,
        "source_features_manifest": {
            "feature_schema_version": dataset.manifest.get("feature_schema_version"),
            "source_dataset": dataset.manifest.get("source_dataset"),
        },
        "selected_model": {
            "model_type": result.ablation.selected.model_type,
            "feature_group": result.ablation.selected.feature_group,
            "hyperparameters": result.ablation.selected.hyperparameters,
            "selected_on": "validation balanced accuracy",
        },
        "ablation": result.ablation.to_json_dict(),
        "persistence_policy": result.persistence_policy.to_json_dict(),
        "reference_baseline": result.reference_baseline.to_json_dict(),
        "validation_metrics": result.validation_metrics.to_json_dict(),
        "test_metrics": result.test_metrics.to_json_dict(),
        "test_operational_metrics": {
            "false_positive_rate_healthy": result.test_false_positive_rate_healthy,
            "detection": result.test_detection.to_json_dict(),
        },
        "runtime": runtime.to_json_dict(),
        "bootstrap_balanced_accuracy_ci": result.bootstrap_ci,
        "statistical_honesty": {
            "run_counts": result.run_counts,
            "fault_run_counts": result.fault_run_counts,
            "severity_band_counts": result.severity_band_counts,
            "note": (
                "The independent experimental units are simulation runs, not "
                "feature rows — with only 4 target-fault runs per class in "
                "validation and test, per-severity-band and per-run detection "
                "metrics for those splits should be read as indicative, not "
                "statistically precise."
            ),
        },
        "plots": [p.filename for p in plots],
        "generation_command": generation_command,
        "limitations": [
            "All data is simulator-generated (Plant Alpha); no real fuel-cell "
            "telemetry has been used to validate these results.",
            "Validation and test splits contain only 4 target-fault runs per "
            "class — severity-band and detection-latency breakdowns within a "
            "split often rest on 1-3 runs.",
            "The persistence-based detection policy and its comparison "
            "(2 vs. 3 consecutive samples) were selected on validation data "
            "only; only the selected policy was applied to test.",
            "No probability calibration, abstention, drift monitoring, or "
            "online serving is implemented — this is an offline baseline "
            "evaluation only.",
        ],
    }


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def _render_ablation_table(result: ExperimentResult) -> list[str]:
    lines = [
        "| Feature set | Logistic regression (val. balanced acc.) | "
        "Histogram GB (val. balanced acc.) |",
        "|---|---|---|",
    ]
    for group in FEATURE_GROUP_NAMES:
        logreg = result.ablation.best_per_group_and_model[
            (group, LOGISTIC_REGRESSION)
        ]
        hgb = result.ablation.best_per_group_and_model[
            (group, HISTOGRAM_GRADIENT_BOOSTING)
        ]
        lines.append(
            f"| {group} — {FEATURE_GROUP_DESCRIPTIONS[group]} | "
            f"{_fmt(logreg.validation_balanced_accuracy)} | "
            f"{_fmt(hgb.validation_balanced_accuracy)} |"
        )
    lines.append("")
    return lines


def _render_per_class_table(metrics_json: dict[str, Any]) -> list[str]:
    lines = ["| Class | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
    for class_name, stats in metrics_json["per_class"].items():
        lines.append(
            f"| {class_name} | {_fmt(stats['precision'])} | {_fmt(stats['recall'])} | "
            f"{_fmt(stats['f1'])} | {stats['support']} |"
        )
    lines.append("")
    return lines


def _render_severity_table(result: ExperimentResult) -> list[str]:
    lines = [
        "| Class | Band | Recall | Rows | Runs | Small sample |",
        "|---|---|---|---|---|---|",
    ]
    for class_label in FAULT_CLASSES:
        for group in result.test_severity_recall[class_label]:
            lines.append(
                f"| {class_label} | {group.group} | {_fmt(group.recall)} | "
                f"{group.row_count} | {group.run_count} | "
                f"{'yes' if group.small_sample else 'no'} |"
            )
    lines.append("")
    return lines


def _render_ramp_table(result: ExperimentResult) -> list[str]:
    lines = [
        "| Class | Phase | Recall | Rows | Runs | Small sample |",
        "|---|---|---|---|---|---|",
    ]
    for class_label in FAULT_CLASSES:
        for group in result.test_ramp_recall[class_label]:
            lines.append(
                f"| {class_label} | {group.group} | {_fmt(group.recall)} | "
                f"{group.row_count} | {group.run_count} | "
                f"{'yes' if group.small_sample else 'no'} |"
            )
    lines.append("")
    return lines


def _render_detection_table(result: ExperimentResult) -> list[str]:
    lines = [
        "| Run | Fault class | Fault start (s) | Detected | Latency (s) |",
        "|---|---|---|---|---|",
    ]
    for r in result.test_detection.run_results:
        latency = "-" if r.latency_seconds is None else f"{r.latency_seconds:.0f}"
        status = "yes" if r.detected else "**MISSED**"
        lines.append(
            f"| {r.simulation_run_id} | {r.fault_class} | "
            f"{r.fault_start_sim_seconds:.0f} | {status} | "
            f"{latency} |"
        )
    lines.append("")
    return lines


def render_evaluation_report(
    *,
    dataset: ExperimentDataset,
    result: ExperimentResult,
    runtime: RuntimeMetrics,
    plots: list[PlotResult],
    generation_command: str,
) -> str:
    lines: list[str] = []
    lines.append("# Baseline Fault-Diagnosis Evaluation Report (PR168)")
    lines.append("")
    lines.append(f"Generation command: `{generation_command}`")
    lines.append("")
    lines.append(
        f"Source feature dataset: `{dataset.manifest['source_dataset']['dataset_id']}` "
        f"(feature schema {dataset.manifest.get('feature_schema_version')})"
    )
    lines.append("")

    lines.append("## 1. Selected model")
    lines.append("")
    selected = result.ablation.selected
    lines.append(f"- **Model**: {selected.model_type}")
    lines.append(f"- **Feature set**: {selected.feature_group}")
    lines.append(f"- **Hyperparameters**: `{selected.hyperparameters}`")
    lines.append(
        "- **Selected on**: validation balanced accuracy "
        f"({_fmt(selected.validation_balanced_accuracy)}), across every "
        "(model, feature-set, hyperparameter) combination tried"
    )
    lines.append(
        f"- **Detection persistence policy selected**: "
        f"{result.persistence_policy.selected_persistence_samples} consecutive "
        "samples (compared against 2 on validation only — see section 5)"
    )
    lines.append("")

    lines.append("## 2. Feature-set ablation")
    lines.append("")
    lines.append(
        "Best validation balanced accuracy per (feature set, model) — answers "
        "whether temporal, cross-signal, and physics-residual features help:"
    )
    lines.append("")
    lines += _render_ablation_table(result)
    lines.append(f"Total configurations tried: {len(result.ablation.all_trials)} "
                 "(every one is recorded in `experiment_summary.json`).")
    lines.append("")

    lines.append("## 3. Validation metrics (selected configuration)")
    lines.append("")
    lines.append(
        f"Balanced accuracy: **{_fmt(result.validation_metrics.balanced_accuracy)}**, "
        f"macro F1: {_fmt(result.validation_metrics.macro_f1)}"
    )
    lines.append("")
    lines += _render_per_class_table(result.validation_metrics.to_json_dict())

    lines.append("## 4. Final test results (touched exactly once)")
    lines.append("")
    lines.append(
        f"Balanced accuracy: **{_fmt(result.test_metrics.balanced_accuracy)}**, "
        f"macro precision: {_fmt(result.test_metrics.macro_precision)}, "
        f"macro recall: {_fmt(result.test_metrics.macro_recall)}, "
        f"macro F1: {_fmt(result.test_metrics.macro_f1)}"
    )
    lines.append("")
    lines += _render_per_class_table(result.test_metrics.to_json_dict())
    lines.append(
        f"90% run-level bootstrap CI for test balanced accuracy: "
        f"[{_fmt(result.bootstrap_ci['lower'])}, {_fmt(result.bootstrap_ci['upper'])}] "
        f"({result.bootstrap_ci['n_runs']} test runs, "
        f"{result.bootstrap_ci['n_resamples']} resamples)."
    )
    lines.append("")

    lines.append("## 5. Operational metrics (test split)")
    lines.append("")
    lines.append(
        f"- False-positive rate on healthy rows: "
        f"{_fmt(result.test_false_positive_rate_healthy)}"
    )
    lines.append(
        f"- False alarms per healthy simulated hour: "
        f"{_fmt(result.test_detection.false_alarms_per_healthy_hour)} "
        f"({result.test_detection.false_alarm_event_count} events over "
        f"{result.test_detection.healthy_hours_evaluated:.2f} healthy hours)"
    )
    lines.append(f"- Missed fault runs: {result.test_detection.missed_runs or 'none'}")
    for threshold, fraction in (
        (30, result.test_detection.detected_within_seconds(30)),
        (60, result.test_detection.detected_within_seconds(60)),
        (120, result.test_detection.detected_within_seconds(120)),
    ):
        lines.append(f"- Detected within {threshold}s: {fraction:.0%} of fault runs")
    lines.append("")
    lines.append("### Detection latency by run")
    lines.append("")
    lines += _render_detection_table(result)

    lines.append("### Recall by severity band")
    lines.append("")
    lines += _render_severity_table(result)

    lines.append("### Recall during ramp vs. post-ramp")
    lines.append("")
    lines += _render_ramp_table(result)

    lines.append("## 6. Runtime")
    lines.append("")
    lines.append(f"- Training time: {runtime.training_seconds:.3f}s")
    lines.append(
        f"- Mean prediction latency: {runtime.mean_prediction_latency_ms:.4f}ms/row, "
        f"p95: {runtime.p95_prediction_latency_ms:.4f}ms/row"
    )
    lines.append(f"- Serialized artifact size: {runtime.artifact_size_bytes:,} bytes")
    lines.append("")

    lines.append("## 7. Reference threshold baseline (descriptive only)")
    lines.append("")
    ref = result.reference_baseline
    lines.append(
        f"Single best-measurement threshold from PR166's methodology, fit on the "
        f"training split only (`{ref.rule.measurement}` {ref.rule.fault_side} "
        f"{ref.rule.threshold:.4f}), binary healthy-vs-anomalous only "
        "(not directly comparable to the multiclass models above):"
    )
    lines.append("")
    lines.append(
        f"- Train balanced accuracy: {_fmt(ref.rule.train_balanced_accuracy)}"
    )
    lines.append(
        f"- Validation balanced accuracy: {_fmt(ref.validation_balanced_accuracy)}"
    )
    lines.append(f"- Test balanced accuracy: {_fmt(ref.test_balanced_accuracy)}")
    lines.append("")

    lines.append("## 8. Statistical honesty")
    lines.append("")
    lines.append(f"- Run counts by split: {result.run_counts}")
    lines.append(f"- Fault-run counts by split and class: {result.fault_run_counts}")
    lines.append(f"- Severity-band run counts by class: {result.severity_band_counts}")
    lines.append(
        "- The independent experimental units are simulation runs, not the "
        "20k+ feature rows — validation/test each have only 4 target-fault "
        "runs per class, so per-band and per-run metrics above are "
        "indicative, not statistically precise (see the small-sample flags "
        "in the tables above)."
    )
    lines.append("")

    lines.append("## 9. Plots")
    lines.append("")
    if not plots:
        lines.append(
            "No plots generated — install the `dataset-analysis` optional "
            "dependency to enable plotting."
        )
        lines.append("")
    for plot in plots:
        lines.append(f"### {plot.title}")
        lines.append("")
        lines.append(f"![{plot.title}](plots/{plot.filename})")
        lines.append("")
        lines.append(plot.caption)
        lines.append("")

    lines.append("## 10. Limitations")
    lines.append("")
    lines.append("- All data is simulator-generated (Plant Alpha); no real fuel-cell "
                  "telemetry has been used to validate these results.")
    lines.append("- Only 4 target-fault runs per class back validation/test "
                  "severity-band and detection-latency breakdowns.")
    lines.append("- The detection persistence policy (2 vs. 3 consecutive samples) "
                  "was compared and selected on validation only.")
    lines.append("- No probability calibration, abstention, drift monitoring, or "
                  "online serving is implemented — offline baseline only.")
    lines.append("")

    return "\n".join(lines) + "\n"

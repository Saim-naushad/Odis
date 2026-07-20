"""Builds `ood_evaluation_summary.json` and `ood_evaluation_report.md`
from already-computed results — no computation happens here (mirrors
`models/report.py`/`alert_policy/report.py`'s own split from `generate.py`).
"""

from __future__ import annotations

from typing import Any

from backend.simulator.dataset.ood.alert_metrics import AlertEvaluationResult
from backend.simulator.dataset.ood.artifacts import FrozenArtifacts
from backend.simulator.dataset.ood.availability_metrics import AvailabilityMetrics
from backend.simulator.dataset.ood.comparison import GeneralizationComparison
from backend.simulator.dataset.ood.data_loading import InsufficientDataSummary
from backend.simulator.dataset.ood.diagnosis_metrics import RowDiagnosisResult
from backend.simulator.dataset.ood.error_analysis import RepresentativeCase
from backend.simulator.dataset.ood.plots import PlotResult
from backend.simulator.dataset.ood.verdict import VerdictResult


def build_summary_json(
    *,
    generation_command: str,
    artifacts: FrozenArtifacts,
    id_dataset_run_count: int,
    ood_dataset_run_count: int,
    id_insufficient_data: InsufficientDataSummary,
    ood_insufficient_data: InsufficientDataSummary,
    id_availability: AvailabilityMetrics,
    ood_availability: AvailabilityMetrics,
    id_diagnosis: RowDiagnosisResult,
    ood_diagnosis: RowDiagnosisResult,
    id_alerts: AlertEvaluationResult,
    ood_alerts: AlertEvaluationResult,
    comparison: GeneralizationComparison,
    verdict: VerdictResult,
) -> dict[str, Any]:
    return {
        "generation_command": generation_command,
        "frozen_artifacts": artifacts.to_json_dict(),
        "id_cohort": {
            "run_count": id_dataset_run_count,
            "insufficient_data": id_insufficient_data.to_json_dict(),
            "availability": id_availability.to_json_dict(),
            "diagnosis": id_diagnosis.to_json_dict(),
            "alerts": id_alerts.to_json_dict(),
        },
        "ood_cohort": {
            "run_count": ood_dataset_run_count,
            "insufficient_data": ood_insufficient_data.to_json_dict(),
            "availability": ood_availability.to_json_dict(),
            "diagnosis": ood_diagnosis.to_json_dict(),
            "alerts": ood_alerts.to_json_dict(),
        },
        "comparison": comparison.to_json_dict(),
        "verdict": verdict.to_json_dict(),
    }


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_markdown_report(
    *,
    generation_command: str,
    artifacts: FrozenArtifacts,
    ood_insufficient_data: InsufficientDataSummary,
    ood_availability: AvailabilityMetrics,
    id_diagnosis: RowDiagnosisResult,
    ood_diagnosis: RowDiagnosisResult,
    id_alerts: AlertEvaluationResult,
    ood_alerts: AlertEvaluationResult,
    comparison: GeneralizationComparison,
    verdict: VerdictResult,
    representative_cases: list[RepresentativeCase],
    plots: list[PlotResult],
) -> str:
    lines: list[str] = []
    lines.append("# PR171 Out-of-Distribution Evaluation Report")
    lines.append("")
    lines.append(f"Generation command: `{generation_command}`")
    lines.append("")
    lines.append(
        "**This is an evaluation-only report.** The PR168 model pipeline and "
        "PR170 alert policy are frozen and unmodified; no retraining, "
        "recalibration, threshold reselection, or OOD-specific normalization "
        "occurred in producing these numbers."
    )
    lines.append("")

    lines.append("## 1. Frozen artifacts")
    lines.append("")
    lines.append(f"- Model type: **{artifacts.model_metadata['model_type']}**")
    lines.append(f"- Feature group: **{artifacts.feature_group}**")
    lines.append(f"- Pipeline sha256: `{artifacts.pipeline_sha256}`")
    lines.append(f"- Alert policy sha256: `{artifacts.alert_policy_sha256}`")
    lines.append(f"- Class order: {list(artifacts.class_order)}")
    c = artifacts.state_machine_config
    lines.append(
        f"- State-machine config: entry_probability={c.entry_probability}, "
        f"entry_persistence={c.entry_persistence}, "
        f"healthy_exit_probability={c.healthy_exit_probability}, "
        f"exit_persistence={c.exit_persistence}"
    )
    lines.append("")

    lines.append("## 2. Insufficient-data rows (PR173 rejection contract)")
    lines.append("")
    lines.append(
        f"{ood_insufficient_data.rejected_row_count}/"
        f"{ood_insufficient_data.total_eligible_rows} "
        f"({ood_insufficient_data.rejection_fraction:.2%}) OOD timestamps were "
        "excluded from `features.parquet` at generation time — every feature "
        "was either finite and schema-compatible, or the row was rejected "
        "with an explicit reason code (`features/safety.py`); no feature is "
        "ever silently null or imputed. By reason: "
        f"{ood_insufficient_data.by_reason_code}. By feature: "
        f"{ood_insufficient_data.by_invalid_feature_name}."
    )
    lines.append("")
    lines.append(
        f"- Valid-feature coverage: **{_fmt(ood_availability.valid_feature_coverage)}**"
    )
    lines.append(
        "- Longest consecutive insufficient-data streak: "
        f"{ood_availability.longest_consecutive_streak_rows} rows "
        f"({ood_availability.longest_consecutive_streak_seconds:.0f}s)"
    )
    lines.append(
        f"- Affected runs/assets: {ood_availability.affected_run_count} / "
        f"{len(ood_availability.affected_asset_ids)}"
    )
    lines.append(
        f"- Class distribution of rejected rows: {ood_availability.class_distribution}"
    )
    lines.append(
        f"- Stage distribution of rejected rows: {ood_availability.stage_distribution}"
    )
    lines.append(
        "- Ramp-stage unavailable fraction: "
        f"{_fmt(ood_availability.ramp_unavailable_fraction)}, post-ramp: "
        f"{_fmt(ood_availability.post_ramp_unavailable_fraction)}"
    )
    lines.append(
        "- Detection opportunities interrupted: "
        f"{ood_availability.detection_opportunities_interrupted}"
    )
    lines.append("")

    lines.append("## 3. Row-level diagnosis (OOD v1, whole cohort)")
    lines.append("")
    m = ood_diagnosis.multiclass_metrics
    lines.append(f"- Balanced accuracy: **{_fmt(m.balanced_accuracy)}**")
    lines.append(f"- Macro F1: **{_fmt(m.macro_f1)}**")
    lines.append(
        "- Healthy-row false-positive rate: "
        f"**{_fmt(ood_diagnosis.healthy_false_positive_rate)}**"
    )
    lines.append("")
    lines.append("| Class | Precision | Recall | F1 | Support |")
    lines.append("|---|---|---|---|---|")
    for cls in m.class_order:
        row = m.per_class[cls]
        lines.append(
            f"| {cls} | {_fmt(row['precision'])} | {_fmt(row['recall'])} | "
            f"{_fmt(row['f1'])} | {row['support']} |"
        )
    lines.append("")

    lines.append("### Severity-band recall (OOD)")
    lines.append("")
    for cls, groups in ood_diagnosis.severity_band_recall.items():
        for g in groups:
            flag = " (small sample)" if g.small_sample else ""
            lines.append(
                f"- {cls}/{g.group}: recall={_fmt(g.recall)}, rows={g.row_count}, "
                f"runs={g.run_count}{flag}"
            )
    lines.append("")

    lines.append("### Ramp / post-ramp stage recall (OOD)")
    lines.append("")
    lines.append(
        "Later OOD fault onset (500-600s) leaves a short post-ramp window "
        "before the 900s run ends — post-ramp sample/run counts below "
        "should be read with that in mind, not over-interpreted."
    )
    for cls, groups in ood_diagnosis.ramp_stage_recall.items():
        for g in groups:
            flag = " (small sample)" if g.small_sample else ""
            lines.append(
                f"- {cls}/{g.group}: recall={_fmt(g.recall)}, rows={g.row_count}, "
                f"runs={g.run_count}{flag}"
            )
    lines.append("")

    lines.append("## 4. Operational alert behavior (OOD v1, whole cohort)")
    lines.append("")
    lines.append(
        f"- False confirmed alert events/healthy-hour: "
        f"**{_fmt(ood_alerts.false_alerts.false_alert_events_per_healthy_hour)}**"
    )
    lines.append(
        f"- Healthy runs with >=1 false alert: "
        f"{len(ood_alerts.false_alerts.healthy_run_ids_with_alert)}"
    )
    lines.append(
        f"- Mean/max false-episode duration: "
        f"{_fmt(ood_alerts.false_alerts.mean_false_episode_duration_seconds)}s / "
        f"{_fmt(ood_alerts.false_alerts.max_false_episode_duration_seconds)}s"
    )
    lines.append(
        f"- Any-fault missed runs: {len(ood_alerts.detection.any_fault_missed_runs)} "
        f"({ood_alerts.detection.any_fault_missed_runs})"
    )
    lines.append(
        f"- Correct-class missed runs: "
        f"{len(ood_alerts.detection.correct_class_missed_runs)} "
        f"({ood_alerts.detection.correct_class_missed_runs})"
    )
    lines.append(
        f"- Incorrect-class alert runs: {ood_alerts.incorrect_class_alert_run_count}"
    )
    lines.append(
        f"- Median correct-class latency: "
        f"{_fmt(ood_alerts.detection.median_correct_class_latency_seconds)}s"
    )
    for t in (30, 60, 120, 240):
        lines.append(
            f"- Detected within {t}s: "
            f"{ood_alerts.detection.detected_within_seconds(t):.0%} of fault runs"
        )
    lines.append("")

    lines.append("## 5. ID vs. OOD comparison")
    lines.append("")
    lines.append(
        "ID = pilot's own held-out test split, scored through this package's "
        "own metric functions (not the original PR168/PR170 report numbers) "
        "for a strictly apples-to-apples comparison."
    )
    lines.append("")
    lines.append("| Metric | ID | OOD | Absolute change | Relative change |")
    lines.append("|---|---|---|---|---|")

    def _row(name: str, delta: Any) -> str:
        rel = delta.relative_change
        rel_str = "n/a" if rel is None else f"{rel:+.1%}"
        return (
            f"| {name} | {_fmt(delta.id_value)} | {_fmt(delta.ood_value)} | "
            f"{_fmt(delta.absolute_change)} | {rel_str} |"
        )

    lines.append(_row("Balanced accuracy", comparison.balanced_accuracy))
    lines.append(_row("Macro F1", comparison.macro_f1))
    lines.append(
        _row("Healthy false-positive rate", comparison.healthy_false_positive_rate)
    )
    for cls, delta in comparison.per_class_recall.items():
        lines.append(_row(f"{cls} recall", delta))
    lines.append(
        _row(
            "False alert events/healthy-hour",
            comparison.false_alert_events_per_healthy_hour,
        )
    )
    lines.append(_row("Any-fault missed runs", comparison.any_fault_missed_run_count))
    lines.append(
        _row("Correct-class missed runs", comparison.correct_class_missed_run_count)
    )
    lines.append(
        _row(
            "Median correct-class latency (s)",
            comparison.median_correct_class_latency_seconds,
        )
    )
    lines.append(_row("Detected within 120s", comparison.detected_within_120s))
    lines.append("")
    lines.append(
        "**Attribution caveat**: OOD v1 combines higher load, hotter initial "
        "state, later fault onset, and doubled sensor noise simultaneously. "
        "Any statement below about *which* shift drove a given change is an "
        "inference from the feature-shift analysis (section 6), not a "
        "controlled, isolated result — no shift was varied independently in "
        "this dataset."
    )
    lines.append("")

    lines.append("## 6. Representative cases")
    lines.append("")
    if not representative_cases:
        lines.append("No representative cases were selected.")
    for case in representative_cases:
        lines.append(f"### {case.category}: {case.simulation_run_id}")
        lines.append("")
        lines.append(f"{case.rationale}")
        lines.append("")

    lines.append("## 7. Plots")
    lines.append("")
    if not plots:
        lines.append(
            "No plots generated — install the `dataset-analysis` optional "
            "dependency to enable plotting."
        )
    for plot in plots:
        lines.append(f"### {plot.title}")
        lines.append("")
        lines.append(f"![{plot.title}](plots/{plot.filename})")
        lines.append("")
        lines.append(plot.caption)
        lines.append("")

    lines.append("## 8. Verdict")
    lines.append("")
    lines.append(f"**{verdict.verdict}**")
    lines.append("")
    lines.append(f"Criteria: {verdict.criteria_description}")
    lines.append("")
    lines.append("Reasons:")
    for reason in verdict.reasons:
        lines.append(f"- {reason}")
    lines.append("")

    lines.append("## 9. Limitations")
    lines.append("")
    lines.append(
        "- OOD v1 combines four shifts at once (see section 5's attribution caveat)."
    )
    lines.append(
        "- Only 16 runs per fault class — per-severity-band and per-stage "
        "breakdowns are indicative, not statistically robust (see the "
        "small-sample flags above)."
    )
    lines.append(
        "- This is simulator-only evidence from Plant Alpha's first-order-lag "
        "physics model, not a claim about a physical PEM fuel-cell plant."
    )
    lines.append("")

    return "\n".join(lines) + "\n"

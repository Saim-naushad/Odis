"""`alert_policy_search.json`, `alert_evaluation_report.md`, and
`artifacts/alert_policy.json` construction (PR170 spec section 9).

Reads only from an already-computed `AlertPolicyExperimentResult` — no
fitting, no filesystem writes here (mirrors `models/report.py` and
`calibration/report.py`'s split from their own `generate.py`).
"""

from __future__ import annotations

from typing import Any

from backend.simulator.dataset.alert_policy.comparison import median_latency_seconds
from backend.simulator.dataset.alert_policy.config import (
    BASE_FEATURE_GROUP,
    BASE_LOGISTIC_REGRESSION_C,
    BASE_MODEL_TYPE,
    COMPARISON_PERSISTENCE_SAMPLES,
)
from backend.simulator.dataset.alert_policy.experiment import (
    AlertPolicyExperimentResult,
)
from backend.simulator.dataset.alert_policy.plots import PlotResult

_UNCALIBRATED_NOTICE = (
    "Native logistic-regression probabilities used throughout this report "
    "are UNCALIBRATED (PR169 found ~10% argmax disagreement and a "
    "materially different probability distribution after sigmoid "
    "calibration). Do not interpret any probability value here as a "
    "literal real-world likelihood — these thresholds are decision-layer "
    "tuning knobs, not calibrated risk estimates."
)


def build_alert_policy_artifact(result: AlertPolicyExperimentResult) -> dict[str, Any]:
    """Deterministic decision-layer configuration only — references the
    PR168 model rather than duplicating its serialized artifact (spec
    section 9)."""
    return {
        "base_model_reference": {
            "model_type": BASE_MODEL_TYPE,
            "feature_group": BASE_FEATURE_GROUP,
            "logistic_regression_c": BASE_LOGISTIC_REGRESSION_C,
            "note": (
                "Refit fresh via build_logistic_regression_pipeline("
                f"{BASE_LOGISTIC_REGRESSION_C}) on feature set "
                f"{BASE_FEATURE_GROUP}, or load PR168's own "
                "artifacts/selected_pipeline.joblib — both are bit-for-bit "
                "identical given the same training data and random seed."
            ),
        },
        "class_order": list(result.class_order),
        "state_machine_config": (
            result.selected_config.to_json_dict() if result.selected_config else None
        ),
        "uncalibrated_notice": _UNCALIBRATED_NOTICE,
    }


def build_alert_policy_search_json(
    result: AlertPolicyExperimentResult,
) -> dict[str, Any]:
    return {
        "uncalibrated_notice": _UNCALIBRATED_NOTICE,
        "validation_baseline": result.validation_baseline.to_json_dict(),
        "policy_search": result.policy_search.to_json_dict(),
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _render_detection_table(result: AlertPolicyExperimentResult) -> list[str]:
    lines = [
        "| Run | Class | Correct-class detected | Correct latency (s) | "
        "Any-fault detected | Incorrect-before-correct | Pre-onset confirmed |",
        "|---|---|---|---|---|---|---|",
    ]
    if result.test_detection is not None:
        for r in result.test_detection.run_results:
            lines.append(
                f"| {r.simulation_run_id} | {r.fault_class} | "
                f"{'yes' if r.correct_class_detected else '**MISSED**'} | "
                f"{_fmt(r.correct_class_latency_seconds)} | "
                f"{'yes' if r.any_fault_detected else 'no'} | "
                f"{'yes' if r.incorrect_class_confirmed_before_correct else 'no'} | "
                f"{'yes' if r.confirmed_active_at_onset else 'no'} |"
            )
    lines.append("")
    return lines


def render_alert_evaluation_report(
    *,
    result: AlertPolicyExperimentResult,
    plots: list[PlotResult],
    generation_command: str,
) -> str:
    lines: list[str] = []
    lines.append("# PR170 Uncalibrated Temporal Alert-State Policy — Evaluation Report")
    lines.append("")
    lines.append(f"Generation command: `{generation_command}`")
    lines.append("")
    lines.append(f"**{_UNCALIBRATED_NOTICE}**")
    lines.append("")

    lines.append("## 1. Selected policy")
    lines.append("")
    if result.selected_config is not None:
        c = result.selected_config
        lines.append(f"- Entry probability: **{c.entry_probability}**")
        lines.append(f"- Entry persistence: **{c.entry_persistence}** samples")
        lines.append(f"- Healthy exit probability: **{c.healthy_exit_probability}**")
        lines.append(f"- Exit persistence: **{c.exit_persistence}** samples")
    else:
        lines.append(
            "**No policy was selected** — every validation candidate either missed "
            "too many fault runs or degraded latency beyond tolerance. See section 2."
        )
    lines.append("")
    lines.append(f"Selection rule: {result.policy_search.selection_rule}")
    lines.append("")

    lines.append("## 2. Validation policy search")
    lines.append("")
    total_candidates = len(result.policy_search.candidates)
    lines.append(f"Total candidates tried: {total_candidates}")
    rejected = sum(1 for c in result.policy_search.candidates if c.rejected)
    lines.append(f"Rejected: {rejected}, survivors: {total_candidates - rejected}")
    lines.append("")
    lines.append(
        f"PR168 row-sequence baseline (N={COMPARISON_PERSISTENCE_SAMPLES}, "
        "recomputed under PR170's event definition), validation:"
    )
    lines.append(
        f"- Median correct-class latency: "
        f"{_fmt(result.policy_search.baseline_median_latency_seconds)}s"
    )
    lines.append(
        f"- False alert events/healthy-hour: "
        f"{_fmt(result.validation_baseline.false_alerts.false_alert_events_per_healthy_hour)}"
    )
    lines.append("")

    lines.append("## 3. Final test results (touched exactly once)")
    lines.append("")
    lines.append("### Row-level (identical to PR168 — never modified by this policy)")
    lines.append("")
    row_balanced_accuracy = result.test_multiclass_metrics.balanced_accuracy
    lines.append(f"Balanced accuracy: **{_fmt(row_balanced_accuracy)}**")
    lines.append("")

    lines.append("### PR170 selected state policy")
    lines.append("")
    if result.test_detection is not None and result.test_false_alerts is not None:
        correct_missed = result.test_detection.correct_class_missed_runs or "none"
        any_missed = result.test_detection.any_fault_missed_runs or "none"
        lines.append(f"- Correct-class missed runs: {correct_missed}")
        lines.append(f"- Any-fault missed runs: {any_missed}")
        lines.append(
            f"- Median correct-class latency: "
            f"{_fmt(result.test_detection.median_correct_class_latency_seconds)}s"
        )
        for t in (30, 60, 120):
            lines.append(
                f"- Detected within {t}s: "
                f"{result.test_detection.detected_within_seconds(t):.0%} of fault runs"
            )
        lines.append(
            f"- False confirmed alert events: "
            f"{result.test_false_alerts.false_confirmed_event_count} "
            f"({_fmt(result.test_false_alerts.false_alert_events_per_healthy_hour)}/healthy-hour)"
        )
        affected = len(result.test_false_alerts.healthy_run_ids_with_alert)
        lines.append(f"- Healthy runs affected: {affected}")
        lines.append(
            f"- Mean/max false-episode duration: "
            f"{_fmt(result.test_false_alerts.mean_false_episode_duration_seconds)}s / "
            f"{_fmt(result.test_false_alerts.max_false_episode_duration_seconds)}s"
        )
    else:
        lines.append("No policy was selected — see section 1.")
    lines.append("")
    lines.append("### Detection detail by run")
    lines.append("")
    lines += _render_detection_table(result)

    lines.append("## 4. PR168 and PR169 comparison")
    lines.append("")
    lines.append(
        "| | PR168 row-sequence (recomputed) | PR170 selected state policy |"
    )
    lines.append("|---|---|---|")

    baseline_median = median_latency_seconds(result.test_baseline.detection)
    selected_median = (
        result.test_detection.median_correct_class_latency_seconds
        if result.test_detection
        else None
    )
    lines.append(
        f"| Median correct-class latency | {_fmt(baseline_median)}s | "
        f"{_fmt(selected_median)}s |"
    )

    baseline_false_alerts = result.test_baseline.false_alerts
    baseline_rate = baseline_false_alerts.false_alert_events_per_healthy_hour
    selected_rate = (
        result.test_false_alerts.false_alert_events_per_healthy_hour
        if result.test_false_alerts
        else None
    )
    lines.append(
        f"| False alert events/healthy-hour | {_fmt(baseline_rate)} | "
        f"{_fmt(selected_rate)} |"
    )

    baseline_affected = len(baseline_false_alerts.healthy_run_ids_with_alert)
    selected_affected = (
        len(result.test_false_alerts.healthy_run_ids_with_alert)
        if result.test_false_alerts
        else "n/a"
    )
    lines.append(
        f"| Healthy runs affected | {baseline_affected} | {selected_affected} |"
    )

    baseline_missed = len(result.test_baseline.detection.missed_runs)
    selected_missed = (
        len(result.test_detection.correct_class_missed_runs)
        if result.test_detection
        else "n/a"
    )
    lines.append(
        f"| Correct-class missed runs | {baseline_missed} | {selected_missed} |"
    )
    lines.append("")
    lines.append(
        "PR169's calibrated policy remains a separate historical reference (not "
        "refit or reselected here): sigmoid calibration changed ~10% of argmax "
        "predictions, dropping row-level balanced accuracy from 0.855 to ~0.77, "
        "with a slower median detection latency (~135s -> ~190s). PR170 achieves "
        "false-alert reduction without touching row-level predictions at all — "
        "a different, non-competing mechanism."
    )
    lines.append("")

    lines.append("## 5. Plots")
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

    lines.append("## 6. Limitations")
    lines.append("")
    lines.append(f"- {_UNCALIBRATED_NOTICE}")
    lines.append(
        "- Only 4 target-fault runs per class in validation and test — "
        "policy-selection and comparison metrics should be read as indicative."
    )
    lines.append(
        "- The latency-degradation and missed-run caps used for policy selection "
        "were chosen for this pilot's run counts and are not universal constants."
    )
    lines.append("")

    return "\n".join(lines) + "\n"

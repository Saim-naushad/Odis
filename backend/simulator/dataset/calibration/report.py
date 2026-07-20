"""`calibration_summary.json`, `policy_search.json`, `decision_policy.json`,
and `uncertainty_report.md` construction (PR169 spec section 9).

Reads only from an already-computed `CalibrationExperimentResult` — no
fitting, no filesystem writes here (mirrors `models/report.py` vs.
`models/generate.py`'s split).
"""

from __future__ import annotations

from typing import Any

from backend.simulator.dataset.calibration.config import (
    BASE_FEATURE_GROUP,
    BASE_LOGISTIC_REGRESSION_C,
    BASE_MODEL_TYPE,
    CALIBRATION_METHOD,
)
from backend.simulator.dataset.calibration.experiment import CalibrationExperimentResult
from backend.simulator.dataset.calibration.plots import PlotResult
from backend.simulator.dataset.calibration.uncertainty_analysis import UncertaintyGroup


def build_decision_policy(result: CalibrationExperimentResult) -> dict[str, Any]:
    """Everything a downstream consumer needs to *apply* the selected
    policy without re-deriving it: class ordering, confidence threshold,
    persistence count, and calibration method metadata (spec section 9's
    "must contain or reference everything necessary to reproduce")."""
    return {
        "model_type": BASE_MODEL_TYPE,
        "feature_group": BASE_FEATURE_GROUP,
        "base_logistic_regression_c": BASE_LOGISTIC_REGRESSION_C,
        "calibration_method": CALIBRATION_METHOD,
        "class_order": list(result.calibrated_model.class_order),
        "confidence_threshold": result.selected_confidence_threshold,
        "persistence_samples": result.selected_persistence_samples,
        "uncertain_label": "uncertain",
        "uncertain_breaks_persistence_sequence": True,
    }


def build_calibration_summary(
    *,
    result: CalibrationExperimentResult,
    training_seconds: float,
    artifact_size_bytes: int,
    plots: list[PlotResult],
    generation_command: str,
) -> dict[str, Any]:
    return {
        "decision_policy": build_decision_policy(result),
        "calibration_metrics": {
            "validation_before": (
                result.validation_calibration_metrics_before.to_json_dict()
            ),
            "validation_after": (
                result.validation_calibration_metrics_after.to_json_dict()
            ),
            "caveat": (
                "validation_before/after are both computed on the same rows "
                "used to fit the sigmoid calibrator — informative for "
                "before/after comparison, not an independent holdout; the "
                "untouched test split is the true held-out check."
            ),
        },
        "confidence_ranking_shift": result.confidence_ranking_shift.to_json_dict(),
        "calibration_classification_impact": (
            result.calibration_classification_impact.to_json_dict()
        ),
        "abstention_validation_grid": [
            c.to_json_dict() for c in result.validation_coverage_grid
        ],
        "validation_uncertainty": result.validation_uncertainty.to_json_dict(),
        "test_results": {
            "multiclass": result.test_multiclass_metrics.to_json_dict(),
            "coverage": result.test_coverage.to_json_dict(),
            "alert_summary": result.test_alert_summary.to_json_dict(),
            "uncertainty": result.test_uncertainty.to_json_dict(),
            "severity_band_recall": {
                cls: [g.to_json_dict() for g in groups]
                for cls, groups in result.test_severity_recall.items()
            },
            "ramp_vs_post_ramp_recall": {
                cls: [g.to_json_dict() for g in groups]
                for cls, groups in result.test_ramp_recall.items()
            },
        },
        "pr168_comparison": {
            "pr168_baseline": result.pr168_baseline.to_json_dict(),
            "pr169_selected": {
                "confidence_threshold": result.selected_confidence_threshold,
                "persistence_samples": result.selected_persistence_samples,
                "multiclass": result.test_multiclass_metrics.to_json_dict(),
                "coverage": result.test_coverage.to_json_dict(),
                "alert_summary": result.test_alert_summary.to_json_dict(),
            },
        },
        "runtime": {
            "training_seconds": training_seconds,
            "mean_prediction_latency_ms": result.mean_prediction_latency_ms,
            "p95_prediction_latency_ms": result.p95_prediction_latency_ms,
            "artifact_size_bytes": artifact_size_bytes,
        },
        "plots": [p.filename for p in plots],
        "generation_command": generation_command,
    }


def build_policy_search_json(result: CalibrationExperimentResult) -> dict[str, Any]:
    return result.policy_search.to_json_dict()


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def _render_uncertainty_groups(groups: list[UncertaintyGroup]) -> list[str]:
    lines = ["| Group | Rows | Uncertain rate | Mean confidence |", "|---|---|---|---|"]
    for g in groups:
        lines.append(
            f"| {g.group} | {g.row_count} | {_fmt(g.uncertain_rate)} | "
            f"{_fmt(g.mean_confidence)} |"
        )
    lines.append("")
    return lines


def render_uncertainty_report(
    *, result: CalibrationExperimentResult, generation_command: str
) -> str:
    lines: list[str] = []
    lines.append("# PR169 Uncertainty Report")
    lines.append("")
    lines.append(f"Generation command: `{generation_command}`")
    lines.append("")

    lines.append("## 1. Confidence ranking shift (validation)")
    lines.append("")
    shift = result.confidence_ranking_shift
    lines.append(
        f"- Before: {list(shift.class_order_by_mean_confidence_before)}"
    )
    lines.append(f"- After: {list(shift.class_order_by_mean_confidence_after)}")
    lines.append(f"- Ranking changed: **{shift.ranking_changed}**")
    lines.append("")

    lines.append(
        "## 2. Calibration's effect on classification (isolated from abstention)"
    )
    lines.append("")
    impact = result.calibration_classification_impact
    lines.append(
        f"- Argmax flip rate (test): {_fmt(impact.argmax_flip_rate)} of rows changed "
        "predicted class purely due to calibration's per-class renormalization"
    )
    lines.append(
        f"- Calibrated-argmax-only balanced accuracy (test, no abstention): "
        f"{_fmt(impact.calibrated_argmax_balanced_accuracy)} vs. PR168 baseline "
        f"{_fmt(result.pr168_baseline.test_multiclass_metrics.balanced_accuracy)}"
    )
    lines.append("")

    lines.append("## 3. Validation uncertainty by group")
    lines.append("")
    lines.append("### Healthy vs. active fault")
    lines.append("")
    lines += _render_uncertainty_groups(result.validation_uncertainty.healthy_vs_fault)
    lines.append("### Ramp vs. post-ramp")
    lines.append("")
    lines += _render_uncertainty_groups(result.validation_uncertainty.ramp_vs_post_ramp)
    lines.append("### Severity band")
    lines.append("")
    lines += _render_uncertainty_groups(result.validation_uncertainty.severity_band)
    lines.append("### Per fault class")
    lines.append("")
    lines += _render_uncertainty_groups(result.validation_uncertainty.per_fault_class)

    lines.append("## 4. Test uncertainty by group (final, untouched-split check)")
    lines.append("")
    lines.append("### Healthy vs. active fault")
    lines.append("")
    lines += _render_uncertainty_groups(result.test_uncertainty.healthy_vs_fault)
    lines.append("### Ramp vs. post-ramp")
    lines.append("")
    lines += _render_uncertainty_groups(result.test_uncertainty.ramp_vs_post_ramp)
    lines.append("### Severity band")
    lines.append("")
    lines += _render_uncertainty_groups(result.test_uncertainty.severity_band)
    lines.append("### Per fault class")
    lines.append("")
    lines += _render_uncertainty_groups(result.test_uncertainty.per_fault_class)

    lines.append("## 5. Interpretation")
    lines.append("")
    cooling = next(
        (
            g
            for g in result.test_uncertainty.per_fault_class
            if g.group == "cooling_degradation"
        ),
        None,
    )
    other_fault_rates = [
        g.uncertain_rate
        for g in result.test_uncertainty.per_fault_class
        if g.group != "cooling_degradation"
    ]
    if cooling is not None and other_fault_rates:
        disproportionate = cooling.uncertain_rate > max(other_fault_rates)
        verdict = (
            "disproportionately more uncertain"
            if disproportionate
            else "not disproportionate"
        )
        lines.append(
            f"- cooling_degradation uncertain rate ({_fmt(cooling.uncertain_rate)}) "
            f"vs. other fault classes (max {_fmt(max(other_fault_rates))}): {verdict}"
        )
    ramp_groups = {g.group: g for g in result.test_uncertainty.ramp_vs_post_ramp}
    if "ramp" in ramp_groups and "post_ramp" in ramp_groups:
        ramp_rate = ramp_groups["ramp"].uncertain_rate
        post_ramp_rate = ramp_groups["post_ramp"].uncertain_rate
        comparison = "is more" if ramp_rate > post_ramp_rate else "is not more"
        lines.append(
            f"- ramp uncertain rate {_fmt(ramp_rate)} vs. post-ramp "
            f"{_fmt(post_ramp_rate)}: the model {comparison} uncertain during "
            "the ramp phase, as physically expected (severity has not yet "
            "reached its configured maximum)"
        )
    severity_groups = {g.group: g for g in result.test_uncertainty.severity_band}
    if "mild" in severity_groups and "severe" in severity_groups:
        mild_rate = severity_groups["mild"].uncertain_rate
        severe_rate = severity_groups["severe"].uncertain_rate
        lines.append(
            f"- mild-severity uncertain rate {_fmt(mild_rate)} vs. severe "
            f"{_fmt(severe_rate)}"
        )
    lines.append("")

    return "\n".join(lines) + "\n"

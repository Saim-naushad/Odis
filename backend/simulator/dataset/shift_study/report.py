"""Builds every PR172 JSON/Markdown output artifact from already-computed
results — no computation happens here (mirrors `ood/report.py`'s own
split from `generate.py`).
"""

from __future__ import annotations

from typing import Any

from backend.simulator.dataset.shift_study.audit_loading import CohortAudit
from backend.simulator.dataset.shift_study.cohort_loading import CohortData
from backend.simulator.dataset.shift_study.interaction_analysis import (
    InteractionFindings,
)
from backend.simulator.dataset.shift_study.plots import PlotResult
from backend.simulator.dataset.shift_study.rankings import ShiftDamage
from backend.simulator.dataset.shift_study.verdict import StudyVerdict


def build_cohort_metrics_json(
    cohorts: dict[str, CohortData],
    damages: dict[str, ShiftDamage],
    audits: dict[str, CohortAudit],
    study_cases: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, cohort in cohorts.items():
        entry: dict[str, Any] = {
            "diagnosis": cohort.ood_diagnosis,
            "alerts": cohort.ood_alerts,
            "insufficient_data": cohort.insufficient_data,
            "availability": cohort.availability,
            "feature_shift": {
                "top_shifted_by_group": cohort.feature_shift.get(
                    "top_shifted_by_group", {}
                ),
                "top_shifted_overall": cohort.feature_shift.get(
                    "top_shifted_overall", []
                ),
            },
            "representative_cases": study_cases.get(name, []),
        }
        if name in damages:
            entry["damage"] = damages[name].to_json_dict()
        if name in audits:
            entry["audit"] = audits[name].to_json_dict()
        result[name] = entry
    return result


def build_cohort_rankings_json(
    damages: dict[str, ShiftDamage], rankings: dict[str, list[str]]
) -> dict[str, Any]:
    return {
        "damages": {name: damage.to_json_dict() for name, damage in damages.items()},
        "rankings_worst_first": rankings,
    }


def build_shift_study_summary(
    *,
    generation_command: str,
    reference_fingerprint: dict[str, str],
    combined_name: str | None,
    isolated_names: list[str],
    rankings: dict[str, list[str]],
    interaction: InteractionFindings,
    verdict: StudyVerdict,
) -> dict[str, Any]:
    return {
        "generation_command": generation_command,
        "frozen_artifact_fingerprint": reference_fingerprint,
        "combined_cohort": combined_name,
        "isolated_cohorts": sorted(isolated_names),
        "rankings_worst_first": rankings,
        "interaction_analysis": interaction.to_json_dict(),
        "verdict": verdict.to_json_dict(),
    }


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_markdown_report(
    *,
    generation_command: str,
    damages: dict[str, ShiftDamage],
    combined_damage: ShiftDamage | None,
    rankings: dict[str, list[str]],
    interaction: InteractionFindings,
    verdict: StudyVerdict,
    invalid_rows: dict[str, Any],
    audits: dict[str, CohortAudit],
    plots: list[PlotResult],
) -> str:
    lines: list[str] = []
    lines.append("# PR172 Isolated Distribution-Shift Study")
    lines.append("")
    lines.append(f"Generation command: `{generation_command}`")
    lines.append("")
    lines.append(
        "**Evaluation-only.** Every metric below is read from already-computed "
        "PR171 `ood` evaluation outputs, scored with the frozen PR168 model and "
        "PR170 alert policy — nothing here retrains, recalibrates, or retunes "
        "anything."
    )
    lines.append("")

    lines.append("## 1. Isolated-shift severity")
    lines.append("")
    lines.append(
        "| Shift | Tier | Balanced accuracy (ID -> OOD) | False alerts/hr | "
        "Any-fault missed runs |"
    )
    lines.append("|---|---|---|---|---|")
    for name in sorted(damages, key=lambda n: -damages[n].balanced_accuracy_drop):
        d = damages[name]
        lines.append(
            f"| {name} | **{d.tier}** | {_fmt(d.balanced_accuracy_id)} -> "
            f"{_fmt(d.balanced_accuracy_ood)} | "
            f"{_fmt(d.false_alert_rate_per_healthy_hour, 2)} | "
            f"{d.any_fault_missed_run_count} |"
        )
    if combined_damage is not None:
        d = combined_damage
        lines.append(
            f"| combined (PR171 OOD v1) | n/a | {_fmt(d.balanced_accuracy_id)} -> "
            f"{_fmt(d.balanced_accuracy_ood)} | "
            f"{_fmt(d.false_alert_rate_per_healthy_hour, 2)} | "
            f"{d.any_fault_missed_run_count} |"
        )
    lines.append("")

    lines.append("## 2. Per-metric rankings (worst first)")
    lines.append("")
    for metric, order in rankings.items():
        lines.append(f"- **{metric}**: {' > '.join(order)}")
    lines.append("")

    lines.append("## 3. Insufficient-data (rejected) feature rows")
    lines.append("")
    for name in invalid_rows["ranked_by_fraction"]:
        finding = invalid_rows["by_cohort"][name]
        lines.append(
            f"- {name}: {finding['rejected_row_count']}/"
            f"{finding['total_eligible_rows']} "
            f"({finding['rejection_fraction']:.2%}), by feature: "
            f"{finding['by_invalid_feature_name']}"
        )
    lines.append("")

    lines.append("## 4. Physical audit")
    lines.append("")
    for name in sorted(audits):
        audit = audits[name]
        lines.append(
            f"- {name}: **{audit.verdict}**, findings >= medium: "
            f"{audit.finding_counts}, mean physical direction consistency: "
            f"{_fmt(audit.mean_physical_direction_consistency, 2)}"
        )
    lines.append("")

    lines.append("## 5. Combined-vs-isolated interaction analysis")
    lines.append("")
    lines.append(interaction.explanation)
    lines.append("")
    lines.append(
        f"**Load/noise compounding**: {interaction.load_noise_compounding_note}"
    )
    lines.append("")
    lines.append(f"**Late onset**: {interaction.late_onset_note}")
    lines.append("")
    lines.append(
        "**Hot start / cooling degradation**: "
        f"{interaction.hot_start_cooling_confusion_note}"
    )
    lines.append("")

    lines.append("## 6. Study verdict")
    lines.append("")
    lines.append(f"- PRIMARY GENERALIZATION FAILURE: **{verdict.primary_failure}**")
    lines.append(f"- SECONDARY FAILURE: **{verdict.secondary_failure or 'none'}**")
    lines.append(f"- MINOR CONTRIBUTORS: {verdict.minor_contributors}")
    lines.append(
        f"- INTERACTION EFFECTS LIKELY: **{verdict.interaction_effects_likely}**"
    )
    lines.append("")
    lines.append(f"### Recommended next direction: {verdict.recommendation}")
    lines.append("")
    lines.append(verdict.recommendation_description)
    lines.append("")
    lines.append("Reasons:")
    for reason in verdict.recommendation_reasons:
        lines.append(f"- {reason}")
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

    lines.append("## 8. Limitations")
    lines.append("")
    lines.append(
        "- Seeds are independent per cohort, not paired — no factorial "
        "experiment varies two shifts together in a controlled way, so every "
        "interaction statement above is inference, not a measured causal effect."
    )
    lines.append(
        "- Only 16 runs per fault class per cohort — rankings and tier "
        "classifications should be read as indicative at this scale."
    )
    lines.append(
        "- This is simulator-only evidence from Plant Alpha's first-order-lag "
        "physics model."
    )
    lines.append("")

    return "\n".join(lines) + "\n"

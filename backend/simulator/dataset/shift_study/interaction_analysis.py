"""Combined-vs-isolated interaction analysis (spec section 8).

Every finding here is derived from the loaded cohort data, not asserted —
but this is still an unpaired, non-factorial design (no dataset varies
two shifts together in a controlled way), so every interaction statement
is explicitly labeled inference, never a measured causal effect. The four
canonical cohort names (`high_load`, `hot_start`, `late_onset`,
`high_noise`) are looked up by convention; a study run with different
cohort names simply skips the shift-specific notes that don't apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.simulator.dataset.shift_study.cohort_loading import CohortData
from backend.simulator.dataset.shift_study.config import INTERACTION_EXPLAINED_TOLERANCE
from backend.simulator.dataset.shift_study.rankings import ShiftDamage

InteractionLikelihood = Literal["yes", "no", "uncertain"]

_RAMP_VS_POST_RAMP_MEANINGFUL_GAP = 0.15
"""If post-ramp recall exceeds ramp-stage recall by more than this, the
late-onset shift's degradation is read as "mainly a shorter evaluable
post-ramp window", not a distinct diagnosis failure."""


@dataclass(frozen=True)
class InteractionFindings:
    combined_balanced_accuracy_drop: float | None
    worst_isolated_shift: str | None
    worst_isolated_balanced_accuracy_drop: float | None
    sum_isolated_balanced_accuracy_drop: float
    interaction_effects_likely: InteractionLikelihood
    explanation: str
    load_noise_compounding_note: str
    late_onset_note: str
    hot_start_cooling_confusion_note: str

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "combined_balanced_accuracy_drop": self.combined_balanced_accuracy_drop,
            "worst_isolated_shift": self.worst_isolated_shift,
            "worst_isolated_balanced_accuracy_drop": (
                self.worst_isolated_balanced_accuracy_drop
            ),
            "sum_isolated_balanced_accuracy_drop": (
                self.sum_isolated_balanced_accuracy_drop
            ),
            "interaction_effects_likely": self.interaction_effects_likely,
            "explanation": self.explanation,
            "load_noise_compounding_note": self.load_noise_compounding_note,
            "late_onset_note": self.late_onset_note,
            "hot_start_cooling_confusion_note": self.hot_start_cooling_confusion_note,
        }


def _combined_vs_worst_single(
    combined_damage: ShiftDamage | None, isolated_damages: dict[str, ShiftDamage]
) -> tuple[float | None, str | None, float | None, float, InteractionLikelihood, str]:
    sum_drop = sum(d.balanced_accuracy_drop for d in isolated_damages.values())
    if combined_damage is None or not isolated_damages:
        return (
            None,
            None,
            None,
            sum_drop,
            "uncertain",
            "no combined-OOD cohort was supplied — interaction cannot be assessed.",
        )

    worst_name = max(
        isolated_damages, key=lambda n: (isolated_damages[n].balanced_accuracy_drop, n)
    )
    worst_drop = isolated_damages[worst_name].balanced_accuracy_drop
    combined_drop = combined_damage.balanced_accuracy_drop

    if worst_drop <= 0.0:
        likelihood: InteractionLikelihood = "uncertain"
        explanation = (
            "every isolated shift showed no balanced-accuracy drop; "
            "interaction cannot be assessed from this metric."
        )
    elif combined_drop <= worst_drop * INTERACTION_EXPLAINED_TOLERANCE:
        likelihood = "no"
        explanation = (
            f"combined balanced-accuracy drop ({combined_drop:.3f}) is within "
            f"{INTERACTION_EXPLAINED_TOLERANCE:.2f}x of the worst single isolated "
            f"shift's own drop ({worst_name}: {worst_drop:.3f}) — approximately "
            "explained by that one shift alone."
        )
    elif combined_drop < sum_drop:
        likelihood = "uncertain"
        explanation = (
            f"combined drop ({combined_drop:.3f}) exceeds the worst single "
            f"isolated shift ({worst_name}: {worst_drop:.3f}) by more than "
            f"{INTERACTION_EXPLAINED_TOLERANCE:.2f}x but stays below the naive "
            f"additive sum of every isolated drop ({sum_drop:.3f}) — some "
            "interaction is plausible but not established by this unpaired design."
        )
    else:
        likelihood = "yes"
        explanation = (
            f"combined drop ({combined_drop:.3f}) meets or exceeds the naive "
            f"additive sum of every isolated shift's drop ({sum_drop:.3f}) — "
            "interaction effects (shifts compounding each other) are likely, "
            "though not measured by a controlled factorial experiment."
        )

    return combined_drop, worst_name, worst_drop, sum_drop, likelihood, explanation


def _load_noise_compounding_note(
    combined_damage: ShiftDamage | None, isolated_damages: dict[str, ShiftDamage]
) -> str:
    high_load = isolated_damages.get("high_load")
    high_noise = isolated_damages.get("high_noise")
    if combined_damage is None or high_load is None or high_noise is None:
        return (
            "high_load and/or high_noise cohorts not supplied — compounding "
            "cannot be assessed."
        )

    combined_rate = combined_damage.false_alert_rate_per_healthy_hour
    dominant_isolated_rate = max(
        high_load.false_alert_rate_per_healthy_hour,
        high_noise.false_alert_rate_per_healthy_hour,
    )
    dominant_name = (
        "high_noise"
        if high_noise.false_alert_rate_per_healthy_hour
        >= high_load.false_alert_rate_per_healthy_hour
        else "high_load"
    )
    dominant_rate = dominant_isolated_rate
    ratio = combined_rate / dominant_rate if dominant_rate > 0 else None
    accuracy_note = (
        f"combined balanced accuracy ({combined_damage.balanced_accuracy_ood:.3f}) is "
        f"lower than either isolated shift alone (high_load: "
        f"{high_load.balanced_accuracy_ood:.3f}, high_noise: "
        f"{high_noise.balanced_accuracy_ood:.3f})"
        if combined_damage.balanced_accuracy_ood
        < min(high_load.balanced_accuracy_ood, high_noise.balanced_accuracy_ood)
        else (
            f"combined balanced accuracy ({combined_damage.balanced_accuracy_ood:.3f}) "
            "is not lower than the worse of the two isolated shifts alone"
        )
    )
    rate_note = (
        f"combined false-alert rate ({combined_rate:.2f}/hr) tracks {dominant_name}'s "
        f"isolated rate ({dominant_isolated_rate:.2f}/hr) closely"
        if ratio is not None and 0.7 <= ratio <= 1.3
        else (
            f"combined false-alert rate ({combined_rate:.2f}/hr) is well above "
            "either isolated rate alone (high_load: "
            f"{high_load.false_alert_rate_per_healthy_hour:.2f}/hr, high_noise: "
            f"{high_noise.false_alert_rate_per_healthy_hour:.2f}/hr)"
        )
    )
    return f"{rate_note}; {accuracy_note}."


def _late_onset_note(cohorts: dict[str, CohortData]) -> str:
    cohort = cohorts.get("late_onset")
    if cohort is None:
        return "late_onset cohort not supplied — cannot assess."

    ramp_stage = cohort.ood_diagnosis.get("ramp_stage_recall", {})
    ramp_values: list[float] = []
    post_ramp_values: list[float] = []
    for groups in ramp_stage.values():
        for group in groups:
            if group["group"] == "ramp":
                ramp_values.append(group["recall"])
            elif group["group"] == "post_ramp":
                post_ramp_values.append(group["recall"])

    if not ramp_values or not post_ramp_values:
        return "late_onset cohort has no ramp/post-ramp breakdown to assess."

    mean_ramp = sum(ramp_values) / len(ramp_values)
    mean_post_ramp = sum(post_ramp_values) / len(post_ramp_values)
    gap = mean_post_ramp - mean_ramp

    if gap > _RAMP_VS_POST_RAMP_MEANINGFUL_GAP:
        return (
            f"post-ramp recall ({mean_post_ramp:.2f}) exceeds ramp-stage recall "
            f"({mean_ramp:.2f}) by {gap:.2f} — degradation reads mainly as a "
            "shorter evaluable post-ramp window (later onset leaves less "
            "fully-developed-fault time in a fixed-duration run), not a "
            "distinct diagnosis failure once the fault fully develops."
        )
    return (
        f"post-ramp recall ({mean_post_ramp:.2f}) is not meaningfully higher than "
        f"ramp-stage recall ({mean_ramp:.2f}) — late onset appears to affect "
        "diagnosis beyond simply reducing the evaluable post-ramp window."
    )


def _hot_start_cooling_confusion_note(cohorts: dict[str, CohortData]) -> str:
    cohort = cohorts.get("hot_start")
    if cohort is None:
        return "hot_start cohort not supplied — cannot assess."

    metrics = cohort.ood_diagnosis["multiclass_metrics"]
    class_order: list[str] = metrics["class_order"]
    confusion = metrics["confusion_matrix"]
    if "healthy" not in class_order:
        return "hot_start cohort has no 'healthy' class in its confusion matrix."

    healthy_index = class_order.index("healthy")
    healthy_row = confusion[healthy_index]
    fault_indices = [i for i, c in enumerate(class_order) if c != "healthy"]
    misclassification_targets = {
        class_order[i]: healthy_row[i] for i in fault_indices
    }
    top_target = max(
        misclassification_targets, key=lambda c: (misclassification_targets[c], c)
    )
    fault_precisions = {
        c: metrics["per_class"][c]["precision"] for c in class_order if c != "healthy"
    }
    lowest_precision_class = min(
        fault_precisions, key=lambda c: (fault_precisions[c], c)
    )

    if (
        top_target == "cooling_degradation"
        and lowest_precision_class == "cooling_degradation"
    ):
        return (
            f"healthy rows are misclassified as cooling_degradation more than any "
            f"other fault class ({misclassification_targets['cooling_degradation']} "
            "rows), and cooling_degradation has the lowest precision among fault "
            f"classes ({fault_precisions['cooling_degradation']:.2f}) — consistent "
            "with hot initial state specifically resembling cooling degradation's "
            "thermal signature."
        )
    return (
        f"healthy-row misclassification under hot_start is dominated by "
        f"{top_target!r} ({misclassification_targets[top_target]} rows), and "
        f"{lowest_precision_class!r} has the lowest fault-class precision "
        f"({fault_precisions[lowest_precision_class]:.2f}) — no disproportionate "
        "confusion toward cooling_degradation specifically was found."
    )


def analyze_interactions(
    *,
    combined_damage: ShiftDamage | None,
    isolated_damages: dict[str, ShiftDamage],
    cohorts: dict[str, CohortData],
) -> InteractionFindings:
    (
        combined_drop,
        worst_name,
        worst_drop,
        sum_drop,
        likelihood,
        explanation,
    ) = _combined_vs_worst_single(combined_damage, isolated_damages)

    return InteractionFindings(
        combined_balanced_accuracy_drop=combined_drop,
        worst_isolated_shift=worst_name,
        worst_isolated_balanced_accuracy_drop=worst_drop,
        sum_isolated_balanced_accuracy_drop=sum_drop,
        interaction_effects_likely=likelihood,
        explanation=explanation,
        load_noise_compounding_note=_load_noise_compounding_note(
            combined_damage, isolated_damages
        ),
        late_onset_note=_late_onset_note(cohorts),
        hot_start_cooling_confusion_note=_hot_start_cooling_confusion_note(cohorts),
    )

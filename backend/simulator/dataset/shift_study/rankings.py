"""Per-shift damage extraction, per-metric ranking, and the four-tier
minor/moderate/major/catastrophic classification (spec sections 6-7).

Every number here is read from an already-computed PR171 evaluation
summary (`CohortData`) — nothing is recomputed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.simulator.dataset.shift_study.cohort_loading import CohortData
from backend.simulator.dataset.shift_study.config import (
    BALANCED_ACCURACY_CATASTROPHIC_FLOOR,
    BALANCED_ACCURACY_MINOR_DROP_CEILING,
    BALANCED_ACCURACY_MODERATE_DROP_CEILING,
    CLASS_RECALL_CATASTROPHIC_FLOOR,
    FALSE_ALERT_RATE_CATASTROPHIC_FLOOR_PER_HEALTHY_HOUR,
    FALSE_ALERT_RATE_MAJOR_FLOOR_PER_HEALTHY_HOUR,
    FALSE_ALERT_RATE_MINOR_CEILING_PER_HEALTHY_HOUR,
    MISSED_RUN_FRACTION_CATASTROPHIC_FLOOR,
    MISSED_RUN_FRACTION_MAJOR_FLOOR,
)

Tier = Literal["minor", "moderate", "major", "catastrophic"]
_TIER_ORDER: tuple[Tier, ...] = ("minor", "moderate", "major", "catastrophic")


def classify_shift(
    *,
    balanced_accuracy_drop: float,
    ood_balanced_accuracy: float,
    false_alert_rate_per_healthy_hour: float,
    missed_run_fraction_by_class: dict[str, float],
    min_fault_class_recall: float,
) -> Tier:
    """Applies `config.SHIFT_CLASSIFICATION_DESCRIPTION`'s rule exactly —
    catastrophic checked first, then major, then moderate, else minor."""
    worst_missed_fraction = (
        max(missed_run_fraction_by_class.values())
        if missed_run_fraction_by_class
        else 0.0
    )

    if (
        min_fault_class_recall <= CLASS_RECALL_CATASTROPHIC_FLOOR
        or worst_missed_fraction > MISSED_RUN_FRACTION_CATASTROPHIC_FLOOR
        or false_alert_rate_per_healthy_hour
        > FALSE_ALERT_RATE_CATASTROPHIC_FLOOR_PER_HEALTHY_HOUR
        or ood_balanced_accuracy <= BALANCED_ACCURACY_CATASTROPHIC_FLOOR
    ):
        return "catastrophic"

    if (
        balanced_accuracy_drop > BALANCED_ACCURACY_MODERATE_DROP_CEILING
        or false_alert_rate_per_healthy_hour
        > FALSE_ALERT_RATE_MAJOR_FLOOR_PER_HEALTHY_HOUR
        or worst_missed_fraction > MISSED_RUN_FRACTION_MAJOR_FLOOR
    ):
        return "major"

    if balanced_accuracy_drop > BALANCED_ACCURACY_MINOR_DROP_CEILING:
        return "moderate"

    if (
        false_alert_rate_per_healthy_hour
        <= FALSE_ALERT_RATE_MINOR_CEILING_PER_HEALTHY_HOUR
        and worst_missed_fraction == 0.0
    ):
        return "minor"

    return "moderate"


@dataclass(frozen=True)
class ShiftDamage:
    name: str
    balanced_accuracy_id: float
    balanced_accuracy_ood: float
    balanced_accuracy_drop: float
    macro_f1_id: float
    macro_f1_ood: float
    macro_f1_drop: float
    healthy_false_positive_rate_id: float
    healthy_false_positive_rate_ood: float
    healthy_false_positive_rate_increase: float
    false_alert_rate_per_healthy_hour: float
    healthy_runs_affected: int
    any_fault_missed_run_count: int
    correct_class_missed_run_count: int
    incorrect_class_alert_run_count: int
    median_correct_class_latency_seconds: float | None
    detected_within_120s: float
    min_fault_class_recall: float
    missed_run_fraction_by_class: dict[str, float]
    tier: Tier

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "balanced_accuracy": {
                "id": self.balanced_accuracy_id,
                "ood": self.balanced_accuracy_ood,
                "drop": self.balanced_accuracy_drop,
            },
            "macro_f1": {
                "id": self.macro_f1_id,
                "ood": self.macro_f1_ood,
                "drop": self.macro_f1_drop,
            },
            "healthy_false_positive_rate": {
                "id": self.healthy_false_positive_rate_id,
                "ood": self.healthy_false_positive_rate_ood,
                "increase": self.healthy_false_positive_rate_increase,
            },
            "false_alert_rate_per_healthy_hour": self.false_alert_rate_per_healthy_hour,
            "healthy_runs_affected": self.healthy_runs_affected,
            "any_fault_missed_run_count": self.any_fault_missed_run_count,
            "correct_class_missed_run_count": self.correct_class_missed_run_count,
            "incorrect_class_alert_run_count": self.incorrect_class_alert_run_count,
            "median_correct_class_latency_seconds": (
                self.median_correct_class_latency_seconds
            ),
            "detected_within_120s": self.detected_within_120s,
            "min_fault_class_recall": self.min_fault_class_recall,
            "missed_run_fraction_by_class": self.missed_run_fraction_by_class,
            "tier": self.tier,
        }


def _missed_run_fraction_by_class(
    cohort: CohortData, fault_classes: tuple[str, ...]
) -> dict[str, float]:
    run_results = cohort.ood_alerts["detection"]["run_results"]
    fractions: dict[str, float] = {}
    for cls in fault_classes:
        class_runs = [r for r in run_results if r["fault_class"] == cls]
        if not class_runs:
            continue
        missed = sum(1 for r in class_runs if not r["any_fault_detected"])
        fractions[cls] = missed / len(class_runs)
    return fractions


def compute_shift_damage(
    name: str, cohort: CohortData, *, fault_classes: tuple[str, ...]
) -> ShiftDamage:
    ood_metrics = cohort.ood_diagnosis["multiclass_metrics"]
    id_metrics = cohort.id_diagnosis["multiclass_metrics"]
    comparison = cohort.comparison
    alerts = cohort.ood_alerts

    missed_fraction = _missed_run_fraction_by_class(cohort, fault_classes)
    min_recall = min(
        ood_metrics["per_class"][cls]["recall"] for cls in fault_classes
    )
    false_alert_rate = alerts["false_alerts"]["false_alert_events_per_healthy_hour"]

    tier = classify_shift(
        balanced_accuracy_drop=-comparison["balanced_accuracy"]["absolute_change"],
        ood_balanced_accuracy=ood_metrics["balanced_accuracy"],
        false_alert_rate_per_healthy_hour=false_alert_rate,
        missed_run_fraction_by_class=missed_fraction,
        min_fault_class_recall=min_recall,
    )

    return ShiftDamage(
        name=name,
        balanced_accuracy_id=id_metrics["balanced_accuracy"],
        balanced_accuracy_ood=ood_metrics["balanced_accuracy"],
        balanced_accuracy_drop=-comparison["balanced_accuracy"]["absolute_change"],
        macro_f1_id=id_metrics["macro_f1"],
        macro_f1_ood=ood_metrics["macro_f1"],
        macro_f1_drop=-comparison["macro_f1"]["absolute_change"],
        healthy_false_positive_rate_id=cohort.id_diagnosis[
            "healthy_false_positive_rate"
        ],
        healthy_false_positive_rate_ood=cohort.ood_diagnosis[
            "healthy_false_positive_rate"
        ],
        healthy_false_positive_rate_increase=comparison[
            "healthy_false_positive_rate"
        ]["absolute_change"],
        false_alert_rate_per_healthy_hour=false_alert_rate,
        healthy_runs_affected=alerts["false_alerts"]["healthy_runs_with_alert"],
        any_fault_missed_run_count=len(alerts["detection"]["any_fault_missed_runs"]),
        correct_class_missed_run_count=len(
            alerts["detection"]["correct_class_missed_runs"]
        ),
        incorrect_class_alert_run_count=alerts["incorrect_class_alert_run_count"],
        median_correct_class_latency_seconds=alerts["detection"][
            "median_correct_class_latency_seconds"
        ],
        detected_within_120s=alerts["detection"]["detected_within_seconds"]["120"],
        min_fault_class_recall=min_recall,
        missed_run_fraction_by_class=missed_fraction,
        tier=tier,
    )


_RANKING_METRICS: dict[str, tuple[str, bool]] = {
    "balanced_accuracy_drop": ("balanced_accuracy_drop", True),
    "macro_f1_drop": ("macro_f1_drop", True),
    "healthy_false_positive_rate_increase": (
        "healthy_false_positive_rate_increase",
        True,
    ),
    "false_alert_rate_per_healthy_hour": ("false_alert_rate_per_healthy_hour", True),
    "any_fault_missed_run_count": ("any_fault_missed_run_count", True),
    "median_correct_class_latency_seconds": (
        "median_correct_class_latency_seconds",
        True,
    ),
}


def rank_shifts(damages: dict[str, ShiftDamage]) -> dict[str, list[str]]:
    """One ranking per required metric (spec section 7), worst-first,
    tie-broken by cohort name for determinism. `None` latencies (no fault
    ever detected) sort last, not first, on the latency ranking."""
    rankings: dict[str, list[str]] = {}
    for metric_name, (attr, worst_is_high) in _RANKING_METRICS.items():

        def _key(
            name: str, attr: str = attr, worst_is_high: bool = worst_is_high
        ) -> tuple[int, float, str]:
            value = getattr(damages[name], attr)
            if value is None:
                return (1, 0.0, name)
            magnitude = value if worst_is_high else -value
            return (0, -magnitude, name)

        rankings[metric_name] = sorted(damages, key=_key)
    return rankings


def tier_rank(tier: Tier) -> int:
    return _TIER_ORDER.index(tier)

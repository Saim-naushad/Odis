"""Promotion decision (spec section 11) — applies
`config.DEFAULT_PROMOTION_THRESHOLDS` to already-computed comparisons.

The thresholds are fixed in `config.py`, defined and committed before this
function is ever called against real evaluation results (spec: "Document
exact thresholds in code before reading final test results") — this
function only ever compares against them, it never derives or adjusts a
threshold from what it observes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.robustness.comparison import CohortComparison
from backend.simulator.dataset.robustness.config import (
    DEFAULT_PROMOTION_THRESHOLDS,
    PromotionThresholds,
)

PROMOTE = "PROMOTE ROBUST MODEL"
KEEP_INSUFFICIENT = "KEEP ORIGINAL MODEL — ROBUSTNESS GAINS INSUFFICIENT"
KEEP_ID_REGRESSION = "KEEP ORIGINAL MODEL — ID REGRESSION TOO LARGE"
NO_MODEL_READY = "NO MODEL READY — FURTHER FEATURE/DATA REVISION REQUIRED"

_VALID_DECISIONS = (PROMOTE, KEEP_INSUFFICIENT, KEEP_ID_REGRESSION, NO_MODEL_READY)


@dataclass(frozen=True)
class PromotionDecision:
    decision: str
    reasons: tuple[str, ...]
    thresholds: PromotionThresholds
    checks: dict[str, Any]

    def __post_init__(self) -> None:
        if self.decision not in _VALID_DECISIONS:
            raise ValueError(
                f"decision must be one of {_VALID_DECISIONS}, got {self.decision!r}"
            )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "thresholds": self.thresholds.to_json_dict(),
            "checks": self.checks,
        }


def decide_promotion(
    *,
    cohort_comparisons: dict[str, CohortComparison],
    fault_classes: tuple[str, ...],
    thresholds: PromotionThresholds = DEFAULT_PROMOTION_THRESHOLDS,
) -> PromotionDecision:
    """`cohort_comparisons` must contain at least "pilot", "high_noise", and
    "combined_ood_v1" — the three cohorts every promotion criterion below
    reads from directly; every other cohort in the mapping is still checked
    for class collapse and missed-run regression, just not for the
    headline balanced-accuracy gates.
    """
    for required in ("pilot", "high_noise", "combined_ood_v1"):
        if required not in cohort_comparisons:
            raise ValueError(
                f"cohort_comparisons is missing the required {required!r} cohort"
            )

    pilot = cohort_comparisons["pilot"]
    high_noise = cohort_comparisons["high_noise"]
    combined_ood = cohort_comparisons["combined_ood_v1"]

    checks: dict[str, Any] = {}

    # --- 1. ID regression (checked first; disqualifies outright) -----------
    pilot_accuracy_drop = -(pilot.balanced_accuracy.absolute_change or 0.0)
    pilot_false_alert_rate = (
        pilot.false_alert_events_per_healthy_hour.robust_value or 0.0
    )
    max_pilot_false_alert_rate = (
        thresholds.max_pilot_false_alert_events_per_healthy_hour
    )
    id_regression_reasons = []
    if pilot_accuracy_drop > thresholds.max_pilot_balanced_accuracy_drop:
        id_regression_reasons.append(
            f"pilot balanced accuracy dropped {pilot_accuracy_drop:.4f}, "
            f"exceeding the {thresholds.max_pilot_balanced_accuracy_drop:.4f} bound"
        )
    if pilot_false_alert_rate > max_pilot_false_alert_rate:
        id_regression_reasons.append(
            f"pilot false-alert rate {pilot_false_alert_rate:.4f} events/healthy-"
            f"hour exceeds the {max_pilot_false_alert_rate:.4f} bound"
        )
    checks["pilot_accuracy_drop"] = pilot_accuracy_drop
    checks["pilot_false_alert_rate"] = pilot_false_alert_rate
    checks["id_regression_reasons"] = id_regression_reasons
    if id_regression_reasons:
        return PromotionDecision(
            decision=KEEP_ID_REGRESSION,
            reasons=tuple(id_regression_reasons),
            thresholds=thresholds,
            checks=checks,
        )

    # --- 2. Class collapse on any cohort (disqualifies outright) ------------
    collapsed: list[str] = []
    for cohort_name, comparison in cohort_comparisons.items():
        for cls in fault_classes:
            delta = comparison.per_class_recall.get(cls)
            if delta is None or delta.robust_value is None:
                continue
            if delta.robust_value <= thresholds.class_recall_collapse_floor:
                collapsed.append(
                    f"{cohort_name}: {cls} recall {delta.robust_value:.4f} <= "
                    f"{thresholds.class_recall_collapse_floor:.4f}"
                )
    checks["class_collapses"] = collapsed
    if collapsed:
        return PromotionDecision(
            decision=NO_MODEL_READY,
            reasons=tuple(collapsed),
            thresholds=thresholds,
            checks=checks,
        )

    # --- 3. Missed-run regression on any cohort -----------------------------
    missed_run_regressions: list[str] = []
    for cohort_name, comparison in cohort_comparisons.items():
        delta = comparison.correct_class_missed_run_count
        if delta.original_value is None or delta.robust_value is None:
            continue
        regression = delta.robust_value - delta.original_value
        if regression > thresholds.max_missed_run_count_regression:
            missed_run_regressions.append(
                f"{cohort_name}: correct-class missed runs increased by "
                f"{regression:.0f}, exceeding the "
                f"{thresholds.max_missed_run_count_regression} bound"
            )
    checks["missed_run_regressions"] = missed_run_regressions

    # --- 4. Required material gains -----------------------------------------
    high_noise_gain = high_noise.balanced_accuracy.absolute_change or 0.0
    combined_ood_gain = combined_ood.balanced_accuracy.absolute_change or 0.0
    high_noise_false_alert_rate = (
        high_noise.false_alert_events_per_healthy_hour.robust_value or 0.0
    )
    checks["high_noise_balanced_accuracy_gain"] = high_noise_gain
    checks["combined_ood_balanced_accuracy_gain"] = combined_ood_gain
    checks["high_noise_false_alert_rate"] = high_noise_false_alert_rate

    insufficient_reasons: list[str] = []
    if high_noise_gain < thresholds.min_high_noise_balanced_accuracy_improvement:
        insufficient_reasons.append(
            f"high-noise balanced-accuracy gain {high_noise_gain:.4f} is below "
            f"the {thresholds.min_high_noise_balanced_accuracy_improvement:.4f} "
            "material-improvement bound"
        )
    if combined_ood_gain < thresholds.min_combined_ood_balanced_accuracy_improvement:
        insufficient_reasons.append(
            "combined-OOD balanced-accuracy gain "
            f"{combined_ood_gain:.4f} is below the "
            f"{thresholds.min_combined_ood_balanced_accuracy_improvement:.4f} "
            "material-improvement bound"
        )
    if (
        high_noise_false_alert_rate
        > thresholds.max_high_noise_false_alert_events_per_healthy_hour
    ):
        insufficient_reasons.append(
            f"high-noise false-alert rate {high_noise_false_alert_rate:.4f} "
            "events/healthy-hour exceeds the "
            f"{thresholds.max_high_noise_false_alert_events_per_healthy_hour:.4f} "
            "bound"
        )
    insufficient_reasons.extend(missed_run_regressions)

    if insufficient_reasons:
        return PromotionDecision(
            decision=KEEP_INSUFFICIENT,
            reasons=tuple(insufficient_reasons),
            thresholds=thresholds,
            checks=checks,
        )

    return PromotionDecision(
        decision=PROMOTE,
        reasons=(
            f"high-noise balanced accuracy improved {high_noise_gain:.4f}",
            f"combined-OOD balanced accuracy improved {combined_ood_gain:.4f}",
            f"pilot balanced-accuracy drop {pilot_accuracy_drop:.4f} stayed within "
            f"the {thresholds.max_pilot_balanced_accuracy_drop:.4f} bound",
            "no fault class collapsed on any evaluated cohort",
            "no cohort's correct-class missed-run count regressed materially",
        ),
        thresholds=thresholds,
        checks=checks,
    )

"""Final PR175 promotion decision (spec section 9) — System C (robust
model + newly selected policy) vs. System A (original model + PR170
policy).

Reuses PR174's exact numeric thresholds (`config.PromotionThresholds`) —
spec section 9 restates the same criteria PR174 already committed to, just
now scored against System C instead of System B — but returns PR175's own
four decision strings, since a "policy insufficient" outcome is a
different claim than PR174's "model gains insufficient" one (the model's
diagnosis gains were already proven sufficient in PR174; this function
only asks whether the *policy* closes the remaining operational gap).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.robustness.comparison import CohortComparison
from backend.simulator.dataset.robustness.config import (
    DEFAULT_PROMOTION_THRESHOLDS,
    PromotionThresholds,
)

PROMOTE = "PROMOTE ROBUST MODEL AND POLICY"
KEEP_POLICY_INSUFFICIENT = "KEEP ORIGINAL MODEL — ALERT POLICY INSUFFICIENT"
KEEP_ID_OPERATIONAL_REGRESSION = "KEEP ORIGINAL MODEL — ID OPERATIONAL REGRESSION"
NO_SYSTEM_MEETS_CRITERIA = "NO SYSTEM MEETS PROMOTION CRITERIA"

_VALID_DECISIONS = (
    PROMOTE,
    KEEP_POLICY_INSUFFICIENT,
    KEEP_ID_OPERATIONAL_REGRESSION,
    NO_SYSTEM_MEETS_CRITERIA,
)


@dataclass(frozen=True)
class PolicyPromotionDecision:
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


def no_policy_selected_decision(
    *, thresholds: PromotionThresholds = DEFAULT_PROMOTION_THRESHOLDS
) -> PolicyPromotionDecision:
    """Spec section 5: "If no policy satisfies the constraints, report no
    selection and keep the original model promoted." Used when
    `policy_search.search_robust_policies` returns `all_rejected=True` —
    there is no System C to even compare, so no cohort evaluation happens
    at all beyond what PR174 already computed for Systems A/B.
    """
    return PolicyPromotionDecision(
        decision=KEEP_POLICY_INSUFFICIENT,
        reasons=(
            "no candidate policy in the search grid survived the validation "
            "rejection rule (zero any-fault misses, at most one correct-class "
            "miss, bounded latency degradation) — see robust_policy_search.json",
        ),
        thresholds=thresholds,
        checks={"policy_search_all_rejected": True},
    )


def decide_policy_promotion(
    *,
    cohort_comparisons: dict[str, CohortComparison],
    fault_classes: tuple[str, ...],
    thresholds: PromotionThresholds = DEFAULT_PROMOTION_THRESHOLDS,
) -> PolicyPromotionDecision:
    """`cohort_comparisons` compares System C (robust model + PR175
    policy) against System A (original model + PR170 policy) on every
    required cohort. Must contain at least "pilot", "high_noise", and
    "combined_ood_v1".
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

    # --- 1. ID operational regression (checked first) -----------------------
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
        return PolicyPromotionDecision(
            decision=KEEP_ID_OPERATIONAL_REGRESSION,
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
        return PolicyPromotionDecision(
            decision=NO_SYSTEM_MEETS_CRITERIA,
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

    # --- 4. Required material gains + operational alert-rate bound ---------
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
        return PolicyPromotionDecision(
            decision=KEEP_POLICY_INSUFFICIENT,
            reasons=tuple(insufficient_reasons),
            thresholds=thresholds,
            checks=checks,
        )

    return PolicyPromotionDecision(
        decision=PROMOTE,
        reasons=(
            f"high-noise balanced accuracy improved {high_noise_gain:.4f}",
            f"combined-OOD balanced accuracy improved {combined_ood_gain:.4f}",
            f"high-noise false-alert rate {high_noise_false_alert_rate:.4f} is at "
            "or below the "
            f"{thresholds.max_high_noise_false_alert_events_per_healthy_hour:.4f} "
            "operational bound",
            f"pilot balanced-accuracy drop {pilot_accuracy_drop:.4f} stayed within "
            f"the {thresholds.max_pilot_balanced_accuracy_drop:.4f} bound",
            f"pilot false-alert rate {pilot_false_alert_rate:.4f} stayed within "
            f"the {max_pilot_false_alert_rate:.4f} bound",
            "no fault class collapsed on any evaluated cohort",
            "no cohort's correct-class missed-run count regressed materially",
        ),
        thresholds=thresholds,
        checks=checks,
    )

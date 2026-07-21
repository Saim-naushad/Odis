"""`decide_policy_promotion` specifications (spec section 9).

Mirrors `test_promotion.py`'s approach: builds `CohortComparison`/
`ModelDelta` objects directly (System C vs. System A) rather than through
`compare_models_on_cohort` — the decision function only ever reads
already-computed deltas.
"""

from __future__ import annotations

import pytest

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.robustness.comparison import CohortComparison, ModelDelta
from backend.simulator.dataset.robustness.config import PromotionThresholds
from backend.simulator.dataset.robustness.policy_generate import REQUIRED_COHORT_NAMES
from backend.simulator.dataset.robustness.policy_promotion import (
    KEEP_ID_OPERATIONAL_REGRESSION,
    KEEP_POLICY_INSUFFICIENT,
    NO_SYSTEM_MEETS_CRITERIA,
    PROMOTE,
    decide_policy_promotion,
    no_policy_selected_decision,
)


def _delta(original: float, robust: float) -> ModelDelta:
    return ModelDelta(original_value=original, robust_value=robust)


def _comparison(
    cohort_name: str,
    *,
    balanced_accuracy: tuple[float, float],
    false_alert_rate: tuple[float, float] = (0.5, 0.1),
    correct_class_missed: tuple[int, int] = (0, 0),
    per_class_recall: dict[str, tuple[float, float]] | None = None,
) -> CohortComparison:
    recall_pairs = per_class_recall or {cls: (0.8, 0.8) for cls in FAULT_CLASSES}
    return CohortComparison(
        cohort_name=cohort_name,
        balanced_accuracy=_delta(*balanced_accuracy),
        macro_f1=_delta(0.7, 0.7),
        healthy_false_positive_rate=_delta(0.1, 0.1),
        per_class_recall={cls: _delta(*pair) for cls, pair in recall_pairs.items()},
        per_class_precision={cls: _delta(0.7, 0.7) for cls in FAULT_CLASSES},
        valid_feature_coverage=_delta(1.0, 1.0),
        false_alert_events_per_healthy_hour=_delta(*false_alert_rate),
        healthy_runs_with_alert_count=_delta(0, 0),
        any_fault_missed_run_count=_delta(0, 0),
        correct_class_missed_run_count=_delta(*correct_class_missed),
        median_correct_class_latency_seconds=_delta(120.0, 110.0),
        detected_within_60s=_delta(0.5, 0.5),
        detected_within_120s=_delta(0.7, 0.7),
        detected_within_240s=_delta(0.9, 0.9),
        insufficient_data_rate=_delta(0.0, 0.0),
    )


def _all_cohorts_comparable(
    **overrides: CohortComparison,
) -> dict[str, CohortComparison]:
    """All 7 PR175 cohorts as a no-op comparison unless overridden."""
    baseline = {
        name: _comparison(name, balanced_accuracy=(0.8, 0.8))
        for name in REQUIRED_COHORT_NAMES
    }
    baseline.update(overrides)
    return baseline


def test_promotes_when_every_criterion_is_met() -> None:
    comparisons = _all_cohorts_comparable(
        pilot=_comparison(
            "pilot", balanced_accuracy=(0.85, 0.885), false_alert_rate=(0.0, 0.0)
        ),
        high_noise=_comparison(
            "high_noise",
            balanced_accuracy=(0.709, 0.855),
            false_alert_rate=(12.08, 0.35),
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1",
            balanced_accuracy=(0.58, 0.743),
            false_alert_rate=(12.06, 0.22),
        ),
    )

    decision = decide_policy_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == PROMOTE


def test_keeps_original_when_high_noise_false_alert_rate_stays_too_high() -> None:
    """This is the exact real-world case PR174's own frozen policy hit:
    large diagnosis gains, but the alert-layer false-alert rate on
    high_noise still exceeds the operational bound — even under a
    supposedly re-selected policy, this must not promote."""
    comparisons = _all_cohorts_comparable(
        pilot=_comparison(
            "pilot", balanced_accuracy=(0.85, 0.88), false_alert_rate=(0.0, 0.0)
        ),
        high_noise=_comparison(
            "high_noise",
            balanced_accuracy=(0.70, 0.85),
            false_alert_rate=(12.0, 1.4),
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1",
            balanced_accuracy=(0.58, 0.74),
            false_alert_rate=(12.0, 0.2),
        ),
    )

    decision = decide_policy_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == KEEP_POLICY_INSUFFICIENT
    assert any("false-alert rate" in reason for reason in decision.reasons)


def test_keeps_original_on_pilot_false_alert_regression() -> None:
    """Pilot (original-regime) false alerts are an ID *operational*
    regression even when pilot balanced accuracy itself improved."""
    comparisons = _all_cohorts_comparable(
        pilot=_comparison(
            "pilot", balanced_accuracy=(0.85, 0.88), false_alert_rate=(0.0, 3.0)
        ),
        high_noise=_comparison(
            "high_noise", balanced_accuracy=(0.70, 0.90), false_alert_rate=(10.0, 0.1)
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1",
            balanced_accuracy=(0.58, 0.80),
            false_alert_rate=(10.0, 0.1),
        ),
    )

    decision = decide_policy_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == KEEP_ID_OPERATIONAL_REGRESSION
    assert any("pilot false-alert rate" in reason for reason in decision.reasons)


def test_keeps_original_on_missed_run_regression() -> None:
    comparisons = _all_cohorts_comparable(
        pilot=_comparison(
            "pilot", balanced_accuracy=(0.85, 0.88), false_alert_rate=(0.0, 0.0)
        ),
        high_noise=_comparison(
            "high_noise",
            balanced_accuracy=(0.70, 0.90),
            false_alert_rate=(10.0, 0.1),
            correct_class_missed=(0, 3),
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1",
            balanced_accuracy=(0.58, 0.80),
            false_alert_rate=(10.0, 0.1),
        ),
    )

    decision = decide_policy_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == KEEP_POLICY_INSUFFICIENT
    assert any("missed runs increased" in reason for reason in decision.reasons)


def test_no_system_meets_criteria_on_class_collapse() -> None:
    comparisons = _all_cohorts_comparable(
        pilot=_comparison(
            "pilot", balanced_accuracy=(0.85, 0.88), false_alert_rate=(0.0, 0.0)
        ),
        high_noise=_comparison(
            "high_noise",
            balanced_accuracy=(0.70, 0.90),
            false_alert_rate=(10.0, 0.1),
            per_class_recall={
                "cooling_degradation": (0.8, 0.1),
                "hydrogen_supply_issue": (0.8, 0.8),
                "sensor_anomaly": (0.8, 0.8),
            },
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1",
            balanced_accuracy=(0.58, 0.80),
            false_alert_rate=(10.0, 0.1),
        ),
    )

    decision = decide_policy_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == NO_SYSTEM_MEETS_CRITERIA
    assert any("cooling_degradation" in reason for reason in decision.reasons)


def test_decide_policy_promotion_requires_the_three_headline_cohorts() -> None:
    with pytest.raises(ValueError, match="high_noise"):
        decide_policy_promotion(
            cohort_comparisons={
                "pilot": _comparison("pilot", balanced_accuracy=(0.8, 0.8)),
                "combined_ood_v1": _comparison(
                    "combined_ood_v1", balanced_accuracy=(0.8, 0.8)
                ),
            },
            fault_classes=FAULT_CLASSES,
        )


def test_no_policy_selected_decision_keeps_original() -> None:
    decision = no_policy_selected_decision()
    assert decision.decision == KEEP_POLICY_INSUFFICIENT
    assert decision.checks["policy_search_all_rejected"] is True


def test_decision_object_rejects_an_invalid_decision_string() -> None:
    with pytest.raises(ValueError):
        from backend.simulator.dataset.robustness.policy_promotion import (
            PolicyPromotionDecision,
        )

        PolicyPromotionDecision(
            decision="NOT A REAL DECISION",
            reasons=(),
            thresholds=PromotionThresholds(),
            checks={},
        )

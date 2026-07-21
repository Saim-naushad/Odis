"""`decide_promotion` specifications (spec section 11).

Every case builds `CohortComparison`/`ModelDelta` objects directly rather
than through `compare_models_on_cohort` — the decision function only ever
reads already-computed deltas, so testing it against hand-built deltas
exercises the actual promotion policy without needing a real dataset for
every branch.
"""

from __future__ import annotations

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.robustness.comparison import CohortComparison, ModelDelta
from backend.simulator.dataset.robustness.config import (
    EXTERNAL_COHORT_NAMES,
    PromotionThresholds,
)
from backend.simulator.dataset.robustness.promotion import (
    KEEP_ID_REGRESSION,
    KEEP_INSUFFICIENT,
    NO_MODEL_READY,
    PROMOTE,
    decide_promotion,
)

_THRESHOLDS = PromotionThresholds()


def _delta(original: float, robust: float) -> ModelDelta:
    return ModelDelta(original_value=original, robust_value=robust)


def _comparison(
    cohort_name: str,
    *,
    balanced_accuracy: tuple[float, float],
    false_alert_rate: tuple[float, float] = (0.5, 0.5),
    correct_class_missed: tuple[int, int] = (0, 0),
    per_class_recall: dict[str, tuple[float, float]] | None = None,
) -> CohortComparison:
    recall_pairs = per_class_recall or {
        cls: (0.8, 0.8) for cls in FAULT_CLASSES
    }
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
    """A full 6-cohort comparison set where every cohort is a no-op
    (identical original/robust metrics) unless overridden."""
    baseline = {
        name: _comparison(name, balanced_accuracy=(0.8, 0.8))
        for name in EXTERNAL_COHORT_NAMES
    }
    baseline.update(overrides)
    return baseline


def test_promotes_when_every_criterion_is_met() -> None:
    comparisons = _all_cohorts_comparable(
        pilot=_comparison("pilot", balanced_accuracy=(0.85, 0.86)),
        high_noise=_comparison(
            "high_noise",
            balanced_accuracy=(0.70, 0.85),
            false_alert_rate=(10.0, 0.5),
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1", balanced_accuracy=(0.58, 0.74)
        ),
    )

    decision = decide_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == PROMOTE


def test_keeps_original_when_gains_are_insufficient() -> None:
    """High-noise/combined-OOD gains below the material-improvement bound
    must not promote, even with no regression anywhere."""
    comparisons = _all_cohorts_comparable(
        pilot=_comparison("pilot", balanced_accuracy=(0.85, 0.86)),
        high_noise=_comparison("high_noise", balanced_accuracy=(0.70, 0.705)),
        combined_ood_v1=_comparison(
            "combined_ood_v1", balanced_accuracy=(0.58, 0.585)
        ),
    )

    decision = decide_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == KEEP_INSUFFICIENT
    assert decision.reasons


def test_keeps_original_when_high_noise_false_alert_rate_stays_too_high() -> None:
    """Mirrors the real evaluation result found on this branch: large
    balanced-accuracy gains but a high-noise false-alert rate that remains
    above the operational bound must not be promoted."""
    comparisons = _all_cohorts_comparable(
        pilot=_comparison("pilot", balanced_accuracy=(0.85, 0.88)),
        high_noise=_comparison(
            "high_noise",
            balanced_accuracy=(0.70, 0.85),
            false_alert_rate=(12.0, 1.4),
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1", balanced_accuracy=(0.58, 0.74)
        ),
    )

    decision = decide_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == KEEP_INSUFFICIENT
    assert any("false-alert rate" in reason for reason in decision.reasons)


def test_keeps_original_on_id_regression_from_accuracy_drop() -> None:
    comparisons = _all_cohorts_comparable(
        pilot=_comparison("pilot", balanced_accuracy=(0.85, 0.80)),
        high_noise=_comparison(
            "high_noise", balanced_accuracy=(0.70, 0.90), false_alert_rate=(10.0, 0.1)
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1", balanced_accuracy=(0.58, 0.80)
        ),
    )

    decision = decide_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == KEEP_ID_REGRESSION
    assert any(
        "pilot balanced accuracy dropped" in reason for reason in decision.reasons
    )


def test_keeps_original_on_id_regression_from_pilot_false_alerts() -> None:
    comparisons = _all_cohorts_comparable(
        pilot=_comparison(
            "pilot", balanced_accuracy=(0.85, 0.86), false_alert_rate=(0.0, 3.0)
        ),
        high_noise=_comparison(
            "high_noise", balanced_accuracy=(0.70, 0.90), false_alert_rate=(10.0, 0.1)
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1", balanced_accuracy=(0.58, 0.80)
        ),
    )

    decision = decide_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == KEEP_ID_REGRESSION
    assert any(
        "pilot false-alert rate" in reason for reason in decision.reasons
    )


def test_no_model_ready_on_any_cohort_class_collapse() -> None:
    """A fault class collapsing on even one cohort (recall at/below the
    collapse floor) disqualifies the candidate outright, regardless of
    otherwise-strong gains — this is a viability failure, not a promotion
    tradeoff."""
    comparisons = _all_cohorts_comparable(
        pilot=_comparison("pilot", balanced_accuracy=(0.85, 0.86)),
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
            "combined_ood_v1", balanced_accuracy=(0.58, 0.80)
        ),
    )

    decision = decide_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == NO_MODEL_READY
    assert any("cooling_degradation" in reason for reason in decision.reasons)


def test_keeps_original_on_missed_run_regression() -> None:
    comparisons = _all_cohorts_comparable(
        pilot=_comparison("pilot", balanced_accuracy=(0.85, 0.86)),
        high_noise=_comparison(
            "high_noise",
            balanced_accuracy=(0.70, 0.90),
            false_alert_rate=(10.0, 0.1),
            correct_class_missed=(0, 3),
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1", balanced_accuracy=(0.58, 0.80)
        ),
    )

    decision = decide_promotion(
        cohort_comparisons=comparisons, fault_classes=FAULT_CLASSES
    )

    assert decision.decision == KEEP_INSUFFICIENT
    assert any("missed runs increased" in reason for reason in decision.reasons)


def test_deterministic_threshold_behavior_at_the_accepting_side_of_every_bound() -> (
    None
):
    """Deterministic tie behavior: this function applies every threshold
    with a plain, unpadded comparison (no ad-hoc epsilon fudge) — landing
    just inside the accepting side of every bound (drop just under the max,
    gains just over the min, false-alert rate just under the max) must
    promote every time, with no dependence on evaluation order or which
    cohort is checked first.
    """
    thresholds = PromotionThresholds()
    margin = 0.001
    comparisons = _all_cohorts_comparable(
        pilot=_comparison(
            "pilot",
            balanced_accuracy=(
                0.85,
                0.85 - (thresholds.max_pilot_balanced_accuracy_drop - margin),
            ),
        ),
        high_noise=_comparison(
            "high_noise",
            balanced_accuracy=(
                0.70,
                0.70 + thresholds.min_high_noise_balanced_accuracy_improvement + margin,
            ),
            false_alert_rate=(
                2.0,
                thresholds.max_high_noise_false_alert_events_per_healthy_hour - margin,
            ),
        ),
        combined_ood_v1=_comparison(
            "combined_ood_v1",
            balanced_accuracy=(
                0.58,
                0.58
                + thresholds.min_combined_ood_balanced_accuracy_improvement
                + margin,
            ),
        ),
    )

    decision = decide_promotion(
        cohort_comparisons=comparisons,
        fault_classes=FAULT_CLASSES,
        thresholds=thresholds,
    )

    assert decision.decision == PROMOTE


def test_decide_promotion_requires_the_three_headline_cohorts() -> None:
    import pytest

    with pytest.raises(ValueError, match="high_noise"):
        decide_promotion(
            cohort_comparisons={
                "pilot": _comparison("pilot", balanced_accuracy=(0.8, 0.8)),
                "combined_ood_v1": _comparison(
                    "combined_ood_v1", balanced_accuracy=(0.8, 0.8)
                ),
            },
            fault_classes=FAULT_CLASSES,
        )

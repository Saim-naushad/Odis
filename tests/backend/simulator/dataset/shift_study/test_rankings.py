"""Shift-damage extraction, tier classification, and per-metric ranking
(spec sections 6-7, and section 13's "degradation classification;
deterministic ranking")."""

from __future__ import annotations

from pathlib import Path

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.shift_study.cohort_loading import load_cohort
from backend.simulator.dataset.shift_study.rankings import (
    classify_shift,
    compute_shift_damage,
    rank_shifts,
)
from tests.backend.simulator.dataset.shift_study.conftest import (
    build_cohort_evaluation_dir,
)


def test_classify_minor() -> None:
    tier = classify_shift(
        balanced_accuracy_drop=0.01,
        ood_balanced_accuracy=0.84,
        false_alert_rate_per_healthy_hour=0.1,
        missed_run_fraction_by_class={},
        min_fault_class_recall=0.8,
    )
    assert tier == "minor"


def test_classify_moderate() -> None:
    tier = classify_shift(
        balanced_accuracy_drop=0.08,
        ood_balanced_accuracy=0.77,
        false_alert_rate_per_healthy_hour=0.1,
        missed_run_fraction_by_class={},
        min_fault_class_recall=0.8,
    )
    assert tier == "moderate"


def test_classify_major_via_balanced_accuracy_drop() -> None:
    tier = classify_shift(
        balanced_accuracy_drop=0.20,
        ood_balanced_accuracy=0.65,
        false_alert_rate_per_healthy_hour=0.1,
        missed_run_fraction_by_class={},
        min_fault_class_recall=0.8,
    )
    assert tier == "major"


def test_classify_major_via_false_alert_rate_alone() -> None:
    tier = classify_shift(
        balanced_accuracy_drop=0.01,
        ood_balanced_accuracy=0.84,
        false_alert_rate_per_healthy_hour=1.5,
        missed_run_fraction_by_class={},
        min_fault_class_recall=0.8,
    )
    assert tier == "major"


def test_classify_catastrophic_via_class_collapse() -> None:
    tier = classify_shift(
        balanced_accuracy_drop=0.01,
        ood_balanced_accuracy=0.84,
        false_alert_rate_per_healthy_hour=0.1,
        missed_run_fraction_by_class={},
        min_fault_class_recall=0.15,
    )
    assert tier == "catastrophic"


def test_classify_catastrophic_via_excessive_false_alerts() -> None:
    tier = classify_shift(
        balanced_accuracy_drop=0.01,
        ood_balanced_accuracy=0.84,
        false_alert_rate_per_healthy_hour=6.0,
        missed_run_fraction_by_class={},
        min_fault_class_recall=0.8,
    )
    assert tier == "catastrophic"


def test_classify_catastrophic_takes_priority_over_major() -> None:
    """A shift meeting both catastrophic and major criteria is
    catastrophic — checked first, per `config.SHIFT_CLASSIFICATION_
    DESCRIPTION`."""
    tier = classify_shift(
        balanced_accuracy_drop=0.30,
        ood_balanced_accuracy=0.30,
        false_alert_rate_per_healthy_hour=10.0,
        missed_run_fraction_by_class={"cooling_degradation": 0.6},
        min_fault_class_recall=0.05,
    )
    assert tier == "catastrophic"


def test_compute_shift_damage_reads_summary_fields_correctly(tmp_path: Path) -> None:
    directory = build_cohort_evaluation_dir(
        tmp_path / "cohort",
        id_balanced_accuracy=0.85,
        ood_balanced_accuracy=0.70,
        false_alert_rate_per_healthy_hour=2.0,
        any_fault_missed_runs=["cooling_degradation-0000"],
    )
    cohort = load_cohort("cohort", directory)
    damage = compute_shift_damage("cohort", cohort, fault_classes=FAULT_CLASSES)

    assert damage.balanced_accuracy_id == 0.85
    assert damage.balanced_accuracy_ood == 0.70
    assert abs(damage.balanced_accuracy_drop - 0.15) < 1e-9
    assert damage.false_alert_rate_per_healthy_hour == 2.0
    assert damage.any_fault_missed_run_count == 1
    assert damage.tier == "major"


def test_rank_shifts_orders_worst_first_and_is_deterministic(tmp_path: Path) -> None:
    damages = {
        "high_load": compute_shift_damage(
            "high_load",
            load_cohort(
                "high_load",
                build_cohort_evaluation_dir(
                    tmp_path / "high_load", ood_balanced_accuracy=0.80
                ),
            ),
            fault_classes=FAULT_CLASSES,
        ),
        "high_noise": compute_shift_damage(
            "high_noise",
            load_cohort(
                "high_noise",
                build_cohort_evaluation_dir(
                    tmp_path / "high_noise", ood_balanced_accuracy=0.60
                ),
            ),
            fault_classes=FAULT_CLASSES,
        ),
        "hot_start": compute_shift_damage(
            "hot_start",
            load_cohort(
                "hot_start",
                build_cohort_evaluation_dir(
                    tmp_path / "hot_start", ood_balanced_accuracy=0.84
                ),
            ),
            fault_classes=FAULT_CLASSES,
        ),
    }

    rankings = rank_shifts(damages)
    assert rankings["balanced_accuracy_drop"] == [
        "high_noise",
        "high_load",
        "hot_start",
    ]

    rankings_again = rank_shifts(damages)
    assert rankings == rankings_again


def test_rank_shifts_sorts_none_latency_last() -> None:
    damages = {
        "a": compute_shift_damage_stub(latency=None),
        "b": compute_shift_damage_stub(latency=50.0),
    }
    rankings = rank_shifts(damages)
    assert rankings["median_correct_class_latency_seconds"] == ["b", "a"]


def compute_shift_damage_stub(*, latency: float | None):  # type: ignore[no-untyped-def]
    from backend.simulator.dataset.shift_study.rankings import ShiftDamage

    return ShiftDamage(
        name="stub",
        balanced_accuracy_id=0.85,
        balanced_accuracy_ood=0.85,
        balanced_accuracy_drop=0.0,
        macro_f1_id=0.8,
        macro_f1_ood=0.8,
        macro_f1_drop=0.0,
        healthy_false_positive_rate_id=0.08,
        healthy_false_positive_rate_ood=0.08,
        healthy_false_positive_rate_increase=0.0,
        false_alert_rate_per_healthy_hour=0.0,
        healthy_runs_affected=0,
        any_fault_missed_run_count=0,
        correct_class_missed_run_count=0,
        incorrect_class_alert_run_count=0,
        median_correct_class_latency_seconds=latency,
        detected_within_120s=0.5,
        min_fault_class_recall=0.8,
        missed_run_fraction_by_class={},
        tier="minor",
    )

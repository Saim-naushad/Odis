"""Study-level verdict: primary/secondary/minor attribution and the A/B/C/D
recommendation (spec section 13, "Verdict")."""

from __future__ import annotations

from backend.simulator.dataset.shift_study.interaction_analysis import (
    InteractionFindings,
)
from backend.simulator.dataset.shift_study.rankings import ShiftDamage, Tier
from backend.simulator.dataset.shift_study.verdict import (
    determine_recommendation,
    determine_study_verdict,
)


def _damage(name: str, tier: Tier, *, drop: float = 0.0) -> ShiftDamage:
    return ShiftDamage(
        name=name,
        balanced_accuracy_id=0.85,
        balanced_accuracy_ood=0.85 - drop,
        balanced_accuracy_drop=drop,
        macro_f1_id=0.8,
        macro_f1_ood=0.8 - drop,
        macro_f1_drop=drop,
        healthy_false_positive_rate_id=0.08,
        healthy_false_positive_rate_ood=0.08,
        healthy_false_positive_rate_increase=0.0,
        false_alert_rate_per_healthy_hour=0.0,
        healthy_runs_affected=0,
        any_fault_missed_run_count=0,
        correct_class_missed_run_count=0,
        incorrect_class_alert_run_count=0,
        median_correct_class_latency_seconds=100.0,
        detected_within_120s=0.5,
        min_fault_class_recall=0.8,
        missed_run_fraction_by_class={},
        tier=tier,
    )


def _no_invalid_rows(names: list[str]) -> dict:
    return {
        "by_cohort": {
            name: {"unscoreable_fraction": 0.0, "unscoreable_row_count": 0}
            for name in names
        },
        "ranked_by_fraction": names,
        "cohort_with_highest_fraction": names[0] if names else None,
    }


def _fake_interaction() -> InteractionFindings:
    return InteractionFindings(
        combined_balanced_accuracy_drop=None,
        worst_isolated_shift=None,
        worst_isolated_balanced_accuracy_drop=None,
        sum_isolated_balanced_accuracy_drop=0.0,
        interaction_effects_likely="uncertain",
        explanation="n/a",
        load_noise_compounding_note="n/a",
        late_onset_note="n/a",
        hot_start_cooling_confusion_note="n/a",
    )


def test_recommendation_a_when_invalid_rows_material() -> None:
    damages = {"high_load": _damage("high_load", "minor")}
    invalid_rows = {
        "by_cohort": {"high_load": {"unscoreable_fraction": 0.05}},
        "ranked_by_fraction": ["high_load"],
    }
    recommendation, reasons = determine_recommendation(damages, invalid_rows)
    assert recommendation == "A"
    assert reasons


def test_recommendation_b_when_high_load_uniquely_dominates() -> None:
    damages = {
        "high_load": _damage("high_load", "major", drop=0.2),
        "hot_start": _damage("hot_start", "moderate", drop=0.08),
        "late_onset": _damage("late_onset", "minor", drop=0.02),
        "high_noise": _damage("high_noise", "moderate", drop=0.1),
    }
    invalid_rows = _no_invalid_rows(list(damages))
    recommendation, _ = determine_recommendation(damages, invalid_rows)
    assert recommendation == "B"


def test_recommendation_c_when_every_shift_moderate() -> None:
    damages = {
        "high_load": _damage("high_load", "moderate", drop=0.08),
        "hot_start": _damage("hot_start", "moderate", drop=0.09),
        "late_onset": _damage("late_onset", "moderate", drop=0.07),
        "high_noise": _damage("high_noise", "moderate", drop=0.1),
    }
    invalid_rows = _no_invalid_rows(list(damages))
    recommendation, _ = determine_recommendation(damages, invalid_rows)
    assert recommendation == "C"


def test_recommendation_d_when_failures_broad_and_severe() -> None:
    damages = {
        "high_load": _damage("high_load", "major", drop=0.2),
        "hot_start": _damage("hot_start", "catastrophic", drop=0.5),
        "late_onset": _damage("late_onset", "major", drop=0.25),
        "high_noise": _damage("high_noise", "catastrophic", drop=0.4),
    }
    invalid_rows = _no_invalid_rows(list(damages))
    recommendation, _ = determine_recommendation(damages, invalid_rows)
    assert recommendation == "D"


def test_recommendation_is_pure_and_deterministic() -> None:
    damages = {
        "high_load": _damage("high_load", "major", drop=0.2),
        "high_noise": _damage("high_noise", "catastrophic", drop=0.4),
    }
    invalid_rows = _no_invalid_rows(list(damages))
    first = determine_recommendation(damages, invalid_rows)
    second = determine_recommendation(damages, invalid_rows)
    assert first == second


def test_primary_and_secondary_failure_selection() -> None:
    damages = {
        "high_load": _damage("high_load", "major", drop=0.2),
        "high_noise": _damage("high_noise", "catastrophic", drop=0.4),
        "hot_start": _damage("hot_start", "minor", drop=0.01),
    }
    invalid_rows = _no_invalid_rows(list(damages))
    result = determine_study_verdict(damages, _fake_interaction(), invalid_rows)
    assert result.primary_failure == "high_noise"
    assert result.secondary_failure == "high_load"
    assert result.minor_contributors == ["hot_start"]


def test_secondary_failure_is_none_when_second_place_is_minor() -> None:
    damages = {
        "high_load": _damage("high_load", "catastrophic", drop=0.5),
        "hot_start": _damage("hot_start", "minor", drop=0.01),
    }
    invalid_rows = _no_invalid_rows(list(damages))
    result = determine_study_verdict(damages, _fake_interaction(), invalid_rows)
    assert result.primary_failure == "high_load"
    assert result.secondary_failure is None


def test_tie_broken_deterministically_by_name() -> None:
    damages = {
        "high_noise": _damage("high_noise", "major", drop=0.2),
        "high_load": _damage("high_load", "major", drop=0.2),
    }
    invalid_rows = _no_invalid_rows(list(damages))
    result = determine_study_verdict(damages, _fake_interaction(), invalid_rows)
    # Equal tier and drop: alphabetically first name wins deterministically.
    assert result.primary_failure == "high_load"
    assert result.secondary_failure == "high_noise"

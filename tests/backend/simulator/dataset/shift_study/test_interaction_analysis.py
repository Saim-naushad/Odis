"""Combined-vs-isolated interaction heuristic (spec section 8/13)."""

from __future__ import annotations

from pathlib import Path

from backend.simulator.dataset.models.config import FAULT_CLASSES
from backend.simulator.dataset.shift_study.cohort_loading import load_cohort
from backend.simulator.dataset.shift_study.interaction_analysis import (
    analyze_interactions,
)
from backend.simulator.dataset.shift_study.rankings import compute_shift_damage
from tests.backend.simulator.dataset.shift_study.conftest import (
    build_cohort_evaluation_dir,
)


def _damage(tmp_path: Path, name: str, *, ood_balanced_accuracy: float):  # type: ignore[no-untyped-def]
    directory = build_cohort_evaluation_dir(
        tmp_path / name, ood_balanced_accuracy=ood_balanced_accuracy
    )
    cohort = load_cohort(name, directory)
    return compute_shift_damage(name, cohort, fault_classes=FAULT_CLASSES)


def test_combined_explained_by_worst_single_shift(tmp_path: Path) -> None:
    isolated = {
        "high_load": _damage(tmp_path, "high_load", ood_balanced_accuracy=0.80),
        "high_noise": _damage(tmp_path, "high_noise", ood_balanced_accuracy=0.65),
    }
    combined = _damage(tmp_path, "combined", ood_balanced_accuracy=0.66)
    findings = analyze_interactions(
        combined_damage=combined, isolated_damages=isolated, cohorts={}
    )
    assert findings.interaction_effects_likely == "no"


def test_interaction_effects_likely_when_combined_exceeds_additive_sum(
    tmp_path: Path,
) -> None:
    isolated = {
        "high_load": _damage(tmp_path, "high_load", ood_balanced_accuracy=0.80),
        "high_noise": _damage(tmp_path, "high_noise", ood_balanced_accuracy=0.75),
    }
    # Isolated drops: 0.05 and 0.10 -> additive sum 0.15. Combined drop 0.30
    # meets/exceeds that sum.
    combined = _damage(tmp_path, "combined", ood_balanced_accuracy=0.55)
    findings = analyze_interactions(
        combined_damage=combined, isolated_damages=isolated, cohorts={}
    )
    assert findings.interaction_effects_likely == "yes"


def test_uncertain_when_combined_between_worst_and_sum(tmp_path: Path) -> None:
    isolated = {
        "high_load": _damage(tmp_path, "high_load", ood_balanced_accuracy=0.80),
        "high_noise": _damage(tmp_path, "high_noise", ood_balanced_accuracy=0.70),
    }
    # Isolated drops: 0.05, 0.15 -> worst=0.15, sum=0.20. Combined drop 0.18
    # is between worst*1.15 (~0.17) and sum (0.20).
    combined = _damage(tmp_path, "combined", ood_balanced_accuracy=0.67)
    findings = analyze_interactions(
        combined_damage=combined, isolated_damages=isolated, cohorts={}
    )
    assert findings.interaction_effects_likely == "uncertain"


def test_missing_combined_cohort_is_handled_gracefully() -> None:
    findings = analyze_interactions(
        combined_damage=None, isolated_damages={}, cohorts={}
    )
    assert findings.interaction_effects_likely == "uncertain"
    assert findings.combined_balanced_accuracy_drop is None


def test_load_noise_compounding_note_requires_both_named_cohorts(
    tmp_path: Path,
) -> None:
    isolated = {"high_load": _damage(tmp_path, "high_load", ood_balanced_accuracy=0.80)}
    combined = _damage(tmp_path, "combined", ood_balanced_accuracy=0.60)
    findings = analyze_interactions(
        combined_damage=combined, isolated_damages=isolated, cohorts={}
    )
    assert "not supplied" in findings.load_noise_compounding_note

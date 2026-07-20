"""Insufficient-data-row rollup (spec section 13, "Invalid-row
analysis")."""

from __future__ import annotations

from pathlib import Path

from backend.simulator.dataset.shift_study.cohort_loading import load_cohorts
from backend.simulator.dataset.shift_study.invalid_rows import aggregate_invalid_rows
from tests.backend.simulator.dataset.shift_study.conftest import (
    build_cohort_evaluation_dir,
)


def test_aggregation_by_cohort(tmp_path: Path) -> None:
    cohorts = load_cohorts(
        [
            (
                "high_noise",
                build_cohort_evaluation_dir(
                    tmp_path / "high_noise",
                    rejected_row_count=385,
                    total_eligible_rows=20224,
                    rejected_by_class={"healthy": 300},
                ),
            ),
            (
                "high_load",
                build_cohort_evaluation_dir(
                    tmp_path / "high_load",
                    rejected_row_count=0,
                    total_eligible_rows=20224,
                ),
            ),
        ]
    )
    result = aggregate_invalid_rows(cohorts)

    assert result["by_cohort"]["high_noise"]["rejected_row_count"] == 385
    assert result["by_cohort"]["high_noise"]["by_class"] == {"healthy": 300}
    assert result["ranked_by_fraction"] == ["high_noise", "high_load"]
    assert result["cohort_with_highest_fraction"] == "high_noise"


def test_zero_invalid_case(tmp_path: Path) -> None:
    cohorts = load_cohorts(
        [
            (
                "high_load",
                build_cohort_evaluation_dir(
                    tmp_path / "high_load", rejected_row_count=0
                ),
            ),
            (
                "late_onset",
                build_cohort_evaluation_dir(
                    tmp_path / "late_onset", rejected_row_count=0
                ),
            ),
        ]
    )
    result = aggregate_invalid_rows(cohorts)
    for finding in result["by_cohort"].values():
        assert finding["rejected_row_count"] == 0
        assert finding["rejection_fraction"] == 0.0
    # Deterministic tie-break by name when fractions are equal.
    assert result["ranked_by_fraction"] == ["high_load", "late_onset"]


def test_by_invalid_feature_name_counts_preserved(tmp_path: Path) -> None:
    cohorts = load_cohorts(
        [
            (
                "high_noise",
                build_cohort_evaluation_dir(
                    tmp_path / "high_noise", rejected_row_count=42
                ),
            )
        ]
    )
    result = aggregate_invalid_rows(cohorts)
    assert (
        result["by_cohort"]["high_noise"]["by_invalid_feature_name"][
            "power_per_fuel_flow"
        ]
        == 42
    )


def test_deterministic_summary(tmp_path: Path) -> None:
    cohorts = load_cohorts(
        [
            (
                "a",
                build_cohort_evaluation_dir(tmp_path / "a", rejected_row_count=10),
            ),
            (
                "b",
                build_cohort_evaluation_dir(tmp_path / "b", rejected_row_count=20),
            ),
        ]
    )
    first = aggregate_invalid_rows(cohorts)
    second = aggregate_invalid_rows(cohorts)
    assert first == second

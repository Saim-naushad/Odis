"""End-to-end `run_shift_study` smoke test on tiny synthetic evaluation
directories (spec section 13, "End-to-end smoke" and "Reproducibility") —
never regenerates real datasets/models, per that section's own guidance.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.simulator.dataset.shift_study.generate import run_shift_study
from tests.backend.simulator.dataset.shift_study.conftest import (
    build_cohort_evaluation_dir,
)


def _build_standard_cohorts(tmp_path: Path) -> dict[str, Path]:
    return {
        "combined": build_cohort_evaluation_dir(
            tmp_path / "combined",
            ood_balanced_accuracy=0.58,
            false_alert_rate_per_healthy_hour=12.3,
            healthy_runs_with_alert=57,
            any_fault_missed_runs=["cooling_degradation-0000"],
        ),
        "high_load": build_cohort_evaluation_dir(
            tmp_path / "high_load",
            ood_balanced_accuracy=0.82,
            false_alert_rate_per_healthy_hour=1.1,
        ),
        "hot_start": build_cohort_evaluation_dir(
            tmp_path / "hot_start",
            ood_balanced_accuracy=0.85,
            false_alert_rate_per_healthy_hour=0.9,
        ),
        "late_onset": build_cohort_evaluation_dir(
            tmp_path / "late_onset",
            ood_balanced_accuracy=0.80,
            false_alert_rate_per_healthy_hour=0.4,
        ),
        "high_noise": build_cohort_evaluation_dir(
            tmp_path / "high_noise",
            ood_balanced_accuracy=0.71,
            false_alert_rate_per_healthy_hour=12.0,
            unscoreable_row_count=385,
            total_rows=20224,
            any_fault_missed_runs=["cooling_degradation-0002"],
        ),
    }


def test_full_study_produces_every_required_artifact(tmp_path: Path) -> None:
    cohorts = _build_standard_cohorts(tmp_path)
    output_dir = tmp_path / "study-output"

    result = run_shift_study(
        combined_ood_evaluation=cohorts.pop("combined"),
        cohort_evaluations=list(cohorts.items()),
        output_directory=output_dir,
        generation_command="test",
    )

    assert (output_dir / "shift_study_summary.json").is_file()
    assert (output_dir / "shift_study_report.md").is_file()
    assert (output_dir / "cohort_metrics.json").is_file()
    assert (output_dir / "cohort_rankings.json").is_file()
    assert (output_dir / "invalid_feature_rows.json").is_file()

    assert result.primary_failure == "high_noise"
    assert result.recommendation in {"A", "B", "C", "D"}

    summary = json.loads((output_dir / "shift_study_summary.json").read_text())
    assert summary["verdict"]["primary_failure"] == "high_noise"
    assert set(summary["frozen_artifact_fingerprint"]) == {
        "pipeline_sha256",
        "alert_policy_sha256",
    }
    assert len(summary["frozen_artifact_fingerprint"]["pipeline_sha256"]) == 64


def test_repeated_study_is_semantically_identical(tmp_path: Path) -> None:
    def _run(output_dir: Path) -> dict[str, object]:
        cohorts = _build_standard_cohorts(output_dir.parent / f"{output_dir.name}-src")
        run_shift_study(
            combined_ood_evaluation=cohorts.pop("combined"),
            cohort_evaluations=list(cohorts.items()),
            output_directory=output_dir,
            generation_command="test",
        )
        summary: dict[str, object] = json.loads(
            (output_dir / "shift_study_summary.json").read_text()
        )
        summary.pop("generation_command")
        return summary

    first = _run(tmp_path / "run1")
    second = _run(tmp_path / "run2")
    assert first == second


def test_missing_cohort_directory_fails_clearly(tmp_path: Path) -> None:
    import pytest

    from backend.simulator.dataset.shift_study.cohort_loading import (
        MissingCohortFileError,
    )

    with pytest.raises(MissingCohortFileError):
        run_shift_study(
            combined_ood_evaluation=None,
            cohort_evaluations=[("high_load", tmp_path / "does-not-exist")],
            output_directory=tmp_path / "output",
            generation_command="test",
        )


def test_output_exists_error_requires_overwrite(tmp_path: Path) -> None:
    import pytest

    from backend.simulator.dataset.shift_study.generate import (
        ShiftStudyOutputExistsError,
    )

    cohorts = _build_standard_cohorts(tmp_path)
    output_dir = tmp_path / "study-output"
    combined = cohorts.pop("combined")
    run_shift_study(
        combined_ood_evaluation=combined,
        cohort_evaluations=list(cohorts.items()),
        output_directory=output_dir,
        generation_command="test",
    )

    with pytest.raises(ShiftStudyOutputExistsError):
        run_shift_study(
            combined_ood_evaluation=combined,
            cohort_evaluations=list(cohorts.items()),
            output_directory=output_dir,
            generation_command="test",
        )

    run_shift_study(
        combined_ood_evaluation=combined,
        cohort_evaluations=list(cohorts.items()),
        output_directory=output_dir,
        overwrite=True,
        generation_command="test",
    )
    assert (output_dir / "shift_study_summary.json").is_file()

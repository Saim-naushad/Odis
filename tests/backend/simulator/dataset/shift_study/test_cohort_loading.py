"""Cohort-evaluation loading: duplicate names, missing files, and
artifact-hash-mismatch rejection (spec section 13, "Comparison" —
"missing cohort handling; duplicate cohort name rejection")."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.simulator.dataset.shift_study.cohort_loading import (
    ArtifactHashMismatchError,
    DuplicateCohortNameError,
    MissingCohortFileError,
    load_cohort,
    load_cohorts,
)
from tests.backend.simulator.dataset.shift_study.conftest import (
    build_cohort_evaluation_dir,
)


def test_load_cohort_reads_all_three_files(tmp_path: Path) -> None:
    directory = build_cohort_evaluation_dir(tmp_path / "cohort-a")
    cohort = load_cohort("cohort-a", directory)
    assert cohort.name == "cohort-a"
    assert cohort.ood_diagnosis["multiclass_metrics"]["balanced_accuracy"] == 0.85
    assert cohort.artifact_fingerprint() == {
        "pipeline_sha256": "a" * 64,
        "alert_policy_sha256": "b" * 64,
    }


def test_missing_evaluation_file_raises(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(MissingCohortFileError):
        load_cohort("empty", empty_dir)


def test_duplicate_cohort_name_rejected(tmp_path: Path) -> None:
    dir_a = build_cohort_evaluation_dir(tmp_path / "a")
    dir_b = build_cohort_evaluation_dir(tmp_path / "b")
    with pytest.raises(DuplicateCohortNameError):
        load_cohorts([("shift", dir_a), ("shift", dir_b)])


def test_missing_cohort_directory_raises_via_load_cohorts(tmp_path: Path) -> None:
    with pytest.raises(MissingCohortFileError):
        load_cohorts([("missing", tmp_path / "does-not-exist")])


def test_artifact_hash_mismatch_rejected(tmp_path: Path) -> None:
    dir_a = build_cohort_evaluation_dir(
        tmp_path / "a", pipeline_sha256="a" * 64, alert_policy_sha256="b" * 64
    )
    dir_b = build_cohort_evaluation_dir(
        tmp_path / "b", pipeline_sha256="c" * 64, alert_policy_sha256="b" * 64
    )
    with pytest.raises(ArtifactHashMismatchError):
        load_cohorts([("high_load", dir_a), ("hot_start", dir_b)])


def test_consistent_artifacts_load_successfully(tmp_path: Path) -> None:
    dir_a = build_cohort_evaluation_dir(tmp_path / "a")
    dir_b = build_cohort_evaluation_dir(tmp_path / "b")
    cohorts = load_cohorts([("high_load", dir_a), ("hot_start", dir_b)])
    assert set(cohorts) == {"high_load", "hot_start"}

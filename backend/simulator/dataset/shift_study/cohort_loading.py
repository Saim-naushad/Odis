"""Loads already-produced PR171 `ood` evaluation directories for the
study (spec section 5: "consume the already-generated cohort evaluation
summaries").
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


class MissingCohortFileError(Exception):
    def __init__(self, cohort_name: str, path: Path) -> None:
        super().__init__(
            f"cohort {cohort_name!r}: required PR171 evaluation output not "
            f"found: {path} — run `python -m backend.simulator.dataset.ood` "
            "against this cohort before including it in the study"
        )
        self.cohort_name = cohort_name
        self.path = path


class DuplicateCohortNameError(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"cohort name {name!r} was supplied more than once")
        self.name = name


class ArtifactHashMismatchError(Exception):
    def __init__(
        self, cohort_name: str, expected: dict[str, str], actual: dict[str, str]
    ) -> None:
        super().__init__(
            f"cohort {cohort_name!r} was evaluated against different frozen "
            f"artifacts than the reference cohort: expected {expected}, got "
            f"{actual} — every cohort in one study must share the identical "
            "frozen PR168 model and PR170 alert policy"
        )
        self.cohort_name = cohort_name


@dataclass(frozen=True)
class CohortData:
    name: str
    evaluation_directory: Path
    summary: dict[str, Any]
    feature_shift: dict[str, Any]
    error_cases: list[dict[str, Any]]

    @property
    def ood_diagnosis(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.summary["ood_cohort"]["diagnosis"])

    @property
    def ood_alerts(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.summary["ood_cohort"]["alerts"])

    @property
    def unscoreable_rows(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.summary["ood_cohort"]["unscoreable_rows"])

    @property
    def id_diagnosis(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.summary["id_cohort"]["diagnosis"])

    @property
    def id_alerts(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.summary["id_cohort"]["alerts"])

    @property
    def comparison(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.summary["comparison"])

    @property
    def verdict(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.summary["verdict"])

    @property
    def frozen_artifacts(self) -> dict[str, Any]:
        return cast(dict[str, Any], self.summary["frozen_artifacts"])

    def artifact_fingerprint(self) -> dict[str, str]:
        return {
            "pipeline_sha256": self.frozen_artifacts["pipeline_sha256"],
            "alert_policy_sha256": self.frozen_artifacts["alert_policy_sha256"],
        }


def _read_json(path: Path, *, cohort_name: str) -> Any:
    if not path.is_file():
        raise MissingCohortFileError(cohort_name, path)
    return json.loads(path.read_text())


def load_cohort(name: str, evaluation_directory: Path) -> CohortData:
    summary = _read_json(
        evaluation_directory / "ood_evaluation_summary.json", cohort_name=name
    )
    feature_shift = _read_json(
        evaluation_directory / "feature_shift.json", cohort_name=name
    )
    error_cases = _read_json(
        evaluation_directory / "error_cases.json", cohort_name=name
    )
    return CohortData(
        name=name,
        evaluation_directory=evaluation_directory,
        summary=summary,
        feature_shift=feature_shift,
        error_cases=error_cases,
    )


def load_cohorts(
    named_directories: Sequence[tuple[str, Path]],
) -> dict[str, CohortData]:
    """Load every cohort, rejecting a duplicate name and verifying every
    cohort was scored against the identical frozen model/alert-policy
    artifacts (spec section 1: "reuse exactly the same" artifacts,
    verified — not merely assumed by convention)."""
    seen_names: set[str] = set()
    cohorts: dict[str, CohortData] = {}
    reference_fingerprint: dict[str, str] | None = None

    for name, directory in named_directories:
        if name in seen_names:
            raise DuplicateCohortNameError(name)
        seen_names.add(name)

        cohort = load_cohort(name, directory)
        fingerprint = cohort.artifact_fingerprint()
        if reference_fingerprint is None:
            reference_fingerprint = fingerprint
        elif fingerprint != reference_fingerprint:
            raise ArtifactHashMismatchError(name, reference_fingerprint, fingerprint)

        cohorts[name] = cohort

    return cohorts

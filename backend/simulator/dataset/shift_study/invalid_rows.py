"""Invalid/unscoreable-feature-row rollup across cohorts (spec section 9).

Reads each cohort's already-computed `unscoreable_rows` summary
(`ood.data_loading.UnscoreableRowSummary.to_json_dict()`, produced by
PR171) — no row-level recomputation happens here. This result is meant to
inform whether PR173 must prioritize numerical feature hardening; it does
not fix anything itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.shift_study.cohort_loading import CohortData


@dataclass(frozen=True)
class InvalidRowFinding:
    cohort: str
    total_rows: int
    unscoreable_row_count: int
    unscoreable_fraction: float
    by_class: dict[str, int]
    by_nullable_column: dict[str, int]
    affected_run_count: int

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "cohort": self.cohort,
            "total_rows": self.total_rows,
            "unscoreable_row_count": self.unscoreable_row_count,
            "unscoreable_fraction": self.unscoreable_fraction,
            "by_class": self.by_class,
            "by_nullable_column": self.by_nullable_column,
            "affected_run_count": self.affected_run_count,
        }


def _finding_for_cohort(name: str, cohort: CohortData) -> InvalidRowFinding:
    rows = cohort.unscoreable_rows
    return InvalidRowFinding(
        cohort=name,
        total_rows=rows["total_rows"],
        unscoreable_row_count=rows["unscoreable_row_count"],
        unscoreable_fraction=rows["unscoreable_fraction"],
        by_class=rows["by_class"],
        by_nullable_column=rows["by_nullable_column"],
        affected_run_count=rows["affected_run_count"],
    )


def aggregate_invalid_rows(cohorts: dict[str, CohortData]) -> dict[str, Any]:
    findings = {
        name: _finding_for_cohort(name, cohort) for name, cohort in cohorts.items()
    }
    ranked_by_fraction = sorted(
        findings, key=lambda name: (-findings[name].unscoreable_fraction, name)
    )
    max_fraction_cohort = ranked_by_fraction[0] if ranked_by_fraction else None
    return {
        "by_cohort": {
            name: finding.to_json_dict() for name, finding in findings.items()
        },
        "ranked_by_fraction": ranked_by_fraction,
        "cohort_with_highest_fraction": max_fraction_cohort,
    }

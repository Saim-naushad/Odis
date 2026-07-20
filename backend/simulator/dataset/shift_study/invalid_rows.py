"""Insufficient-data-row rollup across cohorts (spec section 9).

Reads each cohort's already-computed `insufficient_data`/`availability`
summaries (`ood.data_loading.InsufficientDataSummary`/`ood.availability_
metrics.AvailabilityMetrics`, produced by PR173's rejection contract) —
no row-level recomputation happens here. This result is meant to inform
whether a future PR must prioritize numerical feature hardening; it does
not fix anything itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.shift_study.cohort_loading import CohortData


@dataclass(frozen=True)
class InvalidRowFinding:
    cohort: str
    total_eligible_rows: int
    rejected_row_count: int
    rejection_fraction: float
    by_class: dict[str, int]
    by_reason_code: dict[str, int]
    by_invalid_feature_name: dict[str, int]
    affected_run_count: int

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "cohort": self.cohort,
            "total_eligible_rows": self.total_eligible_rows,
            "rejected_row_count": self.rejected_row_count,
            "rejection_fraction": self.rejection_fraction,
            "by_class": self.by_class,
            "by_reason_code": self.by_reason_code,
            "by_invalid_feature_name": self.by_invalid_feature_name,
            "affected_run_count": self.affected_run_count,
        }


def _finding_for_cohort(name: str, cohort: CohortData) -> InvalidRowFinding:
    rows = cohort.insufficient_data
    availability = cohort.availability
    return InvalidRowFinding(
        cohort=name,
        total_eligible_rows=rows["total_eligible_rows"],
        rejected_row_count=rows["rejected_row_count"],
        rejection_fraction=rows["rejection_fraction"],
        by_class=availability["class_distribution"],
        by_reason_code=rows["by_reason_code"],
        by_invalid_feature_name=rows["by_invalid_feature_name"],
        affected_run_count=rows["affected_run_count"],
    )


def aggregate_invalid_rows(cohorts: dict[str, CohortData]) -> dict[str, Any]:
    findings = {
        name: _finding_for_cohort(name, cohort) for name, cohort in cohorts.items()
    }
    ranked_by_fraction = sorted(
        findings, key=lambda name: (-findings[name].rejection_fraction, name)
    )
    max_fraction_cohort = ranked_by_fraction[0] if ranked_by_fraction else None
    return {
        "by_cohort": {
            name: finding.to_json_dict() for name, finding in findings.items()
        },
        "ranked_by_fraction": ranked_by_fraction,
        "cohort_with_highest_fraction": max_fraction_cohort,
    }

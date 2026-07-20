"""Representative-case selection for the study report (spec section 10).

Reuses PR171's already-computed `error_cases.json` per cohort (produced
by `ood.error_analysis.select_representative_cases`) — this module only
filters down to the four categories the study wants (`successful_easy_
fault`, `delayed_detection`, `missed_fault`, `false_alert_on_healthy_run`)
and skips any that don't exist for a given cohort, never regenerating a
case or a plot from scratch.
"""

from __future__ import annotations

from typing import Any

from backend.simulator.dataset.shift_study.cohort_loading import CohortData

_STUDY_CATEGORIES: tuple[str, ...] = (
    "successful_easy_fault",
    "delayed_detection",
    "missed_fault",
    "false_alert_on_healthy_run",
)


def select_study_cases(
    cohorts: dict[str, CohortData],
) -> dict[str, list[dict[str, Any]]]:
    """One entry per cohort, each a list of at most 4 cases (only the ones
    that exist), in `_STUDY_CATEGORIES` order for determinism."""
    result: dict[str, list[dict[str, Any]]] = {}
    for name, cohort in cohorts.items():
        by_category = {case["category"]: case for case in cohort.error_cases}
        result[name] = [
            by_category[category]
            for category in _STUDY_CATEGORIES
            if category in by_category
        ]
    return result

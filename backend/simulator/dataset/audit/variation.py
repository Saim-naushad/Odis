"""Run-level variation analysis (PR166 spec section 5).

`compute_variation_summary` is pure reporting — the numbers that go into
`summary.json` and the report's variation table/plots. `check_variation`
is the subset of that data worth raising a `Finding` over: identical
same-class configuration, insufficient healthy-run spread, sampled values
escaping the spec's declared ranges, and fault starts landing off the
configured discrete grid.

Split representation per `(class, target_asset)` stratum is *not*
re-checked here: `structural.check_structural` already verifies
`splits.json` byte-for-byte reproduces `splits.assign_splits` given the
manifest's embedded spec, so a second, differently-heuristic check here
would either duplicate that finding or risk disagreeing with it. This
module surfaces the stratum table for the report; see
`compute_variation_summary`'s `stratum_split_counts`.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any

from backend.simulator.dataset.audit.findings import Finding
from backend.simulator.dataset.audit.loader import DatasetHandle
from backend.simulator.dataset.audit.records import DatasetRecords
from backend.simulator.dataset.dataset_spec import DatasetSpec
from backend.simulator.dataset.operating_conditions import OperatingConditionRanges

NUMERIC_FIELDS = (
    "load_baseline_percent",
    "load_amplitude_percent",
    "load_period_seconds",
    "load_phase_radians",
    "initial_load_offset_percent",
    "initial_stack_temperature_offset_celsius",
)

_BOUNDS_TOL = 1e-6
_GRID_TOL = 1e-6
_HEALTHY_SPREAD_MIN_STDEV = 0.5


def _split_by_run_id(splits: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for split_name in ("train", "validation", "test"):
        for run_id in splits.get(split_name, []):
            result[run_id] = split_name
    return result


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
        "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0,
        "distinct": len({round(v, 6) for v in values}),
    }


def compute_variation_summary(
    handle: DatasetHandle, records: DatasetRecords
) -> dict[str, Any]:
    rows = records.runs
    split_by_run_id = _split_by_run_id(handle.splits)

    numeric_stats = {
        field: _stats([row[field] for row in rows]) for field in NUMERIC_FIELDS
    }
    fault_rows = [row for row in rows if row["class_label"] != "normal_operation"]
    numeric_stats["fault_start_sim_seconds"] = _stats(
        [row["fault_start_sim_seconds"] for row in fault_rows]
    )
    numeric_stats["fault_severity"] = _stats(
        [row["fault_severity"] for row in fault_rows]
    )

    stratum_split_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        stratum = f"{row['class_label']}/{row['target_asset_id']}"
        split_name = split_by_run_id.get(row["simulation_run_id"], "unknown")
        stratum_split_counts[stratum][split_name] += 1

    return {
        "numeric": numeric_stats,
        "class_counts": dict(Counter(row["class_label"] for row in rows)),
        "target_asset_counts": dict(Counter(row["target_asset_id"] for row in rows)),
        "split_counts": dict(
            Counter(
                split_by_run_id.get(row["simulation_run_id"], "unknown") for row in rows
            )
        ),
        "stratum_split_counts": {
            stratum: dict(counts) for stratum, counts in stratum_split_counts.items()
        },
    }


def _check_same_class_not_identical(rows: list[dict[str, Any]]) -> list[Finding]:
    by_class: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for row in rows:
        key = (
            *(row[field] for field in NUMERIC_FIELDS),
            row.get("fault_start_sim_seconds"),
            row.get("fault_severity"),
        )
        by_class[row["class_label"]].append(key)

    findings: list[Finding] = []
    for class_label, keys in by_class.items():
        if len(keys) > 1 and len(set(keys)) == 1:
            findings.append(
                Finding(
                    "high",
                    "variation",
                    f"every run of class {class_label!r} has an identical "
                    "resolved configuration — no run-to-run variation",
                )
            )
    return findings


def _check_healthy_spread(rows: list[dict[str, Any]]) -> list[Finding]:
    healthy = [row for row in rows if row["class_label"] == "normal_operation"]
    if len(healthy) < 2:
        return []
    findings: list[Finding] = []
    for field in ("load_baseline_percent", "load_amplitude_percent"):
        stdev = statistics.pstdev([row[field] for row in healthy])
        if stdev < _HEALTHY_SPREAD_MIN_STDEV:
            findings.append(
                Finding(
                    "medium",
                    "variation",
                    f"healthy (normal_operation) runs show little spread in "
                    f"{field} (stdev={stdev:.4f})",
                )
            )
    return findings


def _check_within_bounds(
    rows: list[dict[str, Any]], ranges: OperatingConditionRanges
) -> list[Finding]:
    bound_map = {
        "load_baseline_percent": ranges.load_baseline_percent,
        "load_amplitude_percent": ranges.load_amplitude_percent,
        "load_period_seconds": ranges.load_period_seconds,
        "load_phase_radians": ranges.load_phase_radians,
        "initial_load_offset_percent": ranges.initial_load_offset_percent,
        "initial_stack_temperature_offset_celsius": (
            ranges.initial_stack_temperature_offset_celsius
        ),
    }
    findings: list[Finding] = []
    for field, (low, high) in bound_map.items():
        out_of_bounds = [
            row[field]
            for row in rows
            if row[field] < low - _BOUNDS_TOL or row[field] > high + _BOUNDS_TOL
        ]
        if out_of_bounds:
            findings.append(
                Finding(
                    "blocking",
                    "variation",
                    f"{field} has {len(out_of_bounds)} sampled value(s) "
                    f"outside the declared range [{low}, {high}]",
                    evidence={"examples": out_of_bounds[:5]},
                )
            )
    return findings


def _check_fault_start_grid(
    rows: list[dict[str, Any]], spec: DatasetSpec
) -> list[Finding]:
    plans_by_scenario = {plan.scenario_name.value: plan for plan in spec.scenario_plans}
    off_grid_counts: dict[str, int] = defaultdict(int)
    examples: dict[str, list[float]] = defaultdict(list)

    for row in rows:
        plan = plans_by_scenario.get(row["class_label"])
        if plan is None or plan.fault_start_range is None:
            continue
        start = row["fault_start_sim_seconds"]
        if start is None:
            continue
        grid = plan.fault_start_range
        offset = start - grid.minimum_seconds
        remainder = offset % grid.step_seconds
        on_grid = math.isclose(remainder, 0.0, abs_tol=_GRID_TOL) or math.isclose(
            remainder, grid.step_seconds, abs_tol=_GRID_TOL
        )
        if not on_grid:
            off_grid_counts[row["class_label"]] += 1
            if len(examples[row["class_label"]]) < 5:
                examples[row["class_label"]].append(start)

    return [
        Finding(
            "blocking",
            "variation",
            f"{count} {class_label!r} run(s) have fault_start_sim_seconds "
            "off the configured sampling grid",
            evidence={"examples": examples[class_label]},
        )
        for class_label, count in off_grid_counts.items()
    ]


def check_variation(
    handle: DatasetHandle, records: DatasetRecords
) -> tuple[list[Finding], dict[str, Any]]:
    findings: list[Finding] = []
    findings += _check_same_class_not_identical(records.runs)
    findings += _check_healthy_spread(records.runs)
    findings += _check_within_bounds(
        records.runs, handle.spec.operating_condition_ranges
    )
    findings += _check_fault_start_grid(records.runs, handle.spec)
    summary = compute_variation_summary(handle, records)
    return findings, summary

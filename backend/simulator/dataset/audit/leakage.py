"""Leakage audit (PR166 spec section 8).

Tests each candidate leakage source explicitly rather than running a
generic correlation scan over every column, so every finding names the
concrete mechanism (why the column encodes class) rather than just a
correlation number. Two outcomes are kept distinct throughout:

- **must-exclude metadata** — fields that encode the label *by
  construction* (the run ID, the fault-window columns) because they *are*
  the label or its bookkeeping, not because of a generation bug. These are
  permanent entries on `ALWAYS_EXCLUDE_FROM_FEATURES`, not something a
  future PR "fixes."
- **generation-policy leakage** — an imbalance that *could* be corrected in
  a future dataset spec (e.g. a class concentrated on one target asset).
  These produce their own `Finding`, distinct from the fixed exclusion
  list.

`build_feature_exclusion_list` is what section 8 calls "a future
feature-exclusion list" — the columns a PR167+ feature-engineering pass
must never feed to a model.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.simulator.dataset.audit.findings import Finding
from backend.simulator.dataset.audit.loader import DatasetHandle
from backend.simulator.dataset.audit.records import DatasetRecords

ALWAYS_EXCLUDE_FROM_FEATURES: tuple[str, ...] = (
    "simulation_run_id",
    "dataset_id",
    "class_label",
    "seed",
    "run_start_time",
    "fault_start_sim_seconds",
    "fault_duration_sim_seconds",
    "fault_severity",
    "sensor_noise_json",
    "status",
    "error_message",
)
"""`runs.parquet` columns that encode the label (or run bookkeeping) by
construction — see `check_leakage`'s per-field reasoning below."""


def _split_by_run_id(splits: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for split_name in ("train", "validation", "test"):
        for run_id in splits.get(split_name, []):
            result[run_id] = split_name
    return result


def check_leakage(
    handle: DatasetHandle, records: DatasetRecords
) -> tuple[list[Finding], dict[str, Any]]:
    findings: list[Finding] = []
    rows = records.runs
    notes: dict[str, str] = {}

    # 1. run ID string — perfect leakage by construction (run_plan._run_id
    # embeds the scenario name literally).
    findings.append(
        Finding(
            "low",
            "leakage",
            "simulation_run_id embeds the class name by construction "
            "(`{dataset_id}-{scenario_name}-{index:04d}`) and is a perfect "
            "class predictor — must-exclude metadata, not a generation bug "
            "(informational: no dataset change required)",
        )
    )
    notes["run_id_string"] = "must-exclude metadata (embeds class by construction)"

    # 2. dataset_id — constant within one dataset, carries no information.
    if len({row["dataset_id"] for row in rows}) <= 1:
        notes["dataset_id"] = "constant across every run — cannot encode class"

    # 3. target_asset_id balance
    assets_by_class: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        assets_by_class[row["class_label"]].add(row["target_asset_id"])
    all_assets = set(handle.spec.target_asset_ids)
    unbalanced = {
        cls: sorted(all_assets - assets)
        for cls, assets in assets_by_class.items()
        if assets != all_assets
    }
    if unbalanced:
        findings.append(
            Finding(
                "high",
                "leakage",
                "generation-policy leakage: some class(es) are missing runs "
                "on at least one target asset, so target_asset_id partially "
                "predicts class",
                evidence={"missing_assets_by_class": unbalanced},
            )
        )
        notes["target_asset_id"] = "imbalanced — see finding"
    else:
        notes["target_asset_id"] = (
            "every class is represented on every target asset — no leakage"
        )

    # 4. split assignment vs class
    split_by_run_id = _split_by_run_id(handle.splits)
    class_by_split: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        split_name = split_by_run_id.get(row["simulation_run_id"])
        if split_name is not None:
            class_by_split[split_name].add(row["class_label"])
    all_classes = {row["class_label"] for row in rows}
    missing_from_split = {
        split_name: sorted(all_classes - present)
        for split_name, present in class_by_split.items()
        if present != all_classes
    }
    if missing_from_split:
        findings.append(
            Finding(
                "medium",
                "leakage",
                "generation-policy leakage: at least one split is missing "
                "runs from a class present elsewhere, so split assignment "
                "partially predicts class",
                evidence={"missing_classes_by_split": missing_from_split},
            )
        )
        notes["split_assignment"] = "class missing from a split — see finding"
    else:
        notes["split_assignment"] = (
            "every split contains every class — no split/class leakage"
        )

    # 5. run duration
    if len({row["duration_sim_seconds"] for row in rows}) <= 1:
        notes["run_duration"] = "constant across every run — cannot encode class"
    else:
        by_class = defaultdict(set)
        for row in rows:
            by_class[row["class_label"]].add(row["duration_sim_seconds"])
        if any(len(values) == 1 for values in by_class.values()) and len(
            {v for values in by_class.values() for v in values}
        ) > 1:
            findings.append(
                Finding(
                    "high",
                    "leakage",
                    "duration_sim_seconds varies and is constant within at "
                    "least one class — could predict class",
                )
            )
        notes["run_duration"] = "varies across runs — see evidence"

    # 6. row/sample counts
    sample_counts_by_class: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        sample_counts_by_class[row["class_label"]].add(row["sample_count"])
    distinct_overall = {v for values in sample_counts_by_class.values() for v in values}
    if len(distinct_overall) > 1:
        findings.append(
            Finding(
                "medium",
                "leakage",
                "sample_count/observation_count is not constant across runs "
                "— check whether it correlates with class before using row "
                "counts as a feature",
                evidence={
                    "distinct_counts_by_class": {
                        cls: sorted(values)
                        for cls, values in sample_counts_by_class.items()
                    }
                },
            )
        )
        notes["row_count"] = "varies — see finding"
    else:
        notes["row_count"] = "constant across every run — cannot encode class"

    # 7. run_start_time
    if len({row["run_start_time"] for row in rows}) <= 1:
        notes["run_start_time"] = (
            "identical anchor for every run — cannot encode class"
        )
    else:
        notes["run_start_time"] = (
            "varies across runs — review before using as a feature"
        )

    # 8. missingness pattern — the fault-window columns ARE the label.
    findings.append(
        Finding(
            "low",
            "leakage",
            "runs.parquet's fault_start_sim_seconds/fault_duration_sim_seconds/"
            "fault_severity (and ground_truth.parquet's equivalents) are null "
            "for healthy runs and non-null for fault runs by construction — "
            "a perfect healthy-vs-fault predictor because these columns "
            "encode the label's own timing, not a physical measurement. "
            "Must-exclude metadata, not a defect (informational: no dataset "
            "change required).",
        )
    )
    notes["missingness_pattern"] = "fault-window columns are must-exclude metadata"

    # 9. sensor noise configuration
    if len({row["sensor_noise_json"] for row in rows}) <= 1:
        notes["noise_configuration"] = (
            "identical sensor_noise config for every run — cannot encode class"
        )
    else:
        notes["noise_configuration"] = (
            "varies across runs — review before using as a feature"
        )

    # 10. measurement availability
    measurement_sets_by_run: dict[str, set[str]] = defaultdict(set)
    for row in records.telemetry:
        measurement_sets_by_run[row["simulation_run_id"]].add(row["measurement_type"])
    distinct_measurement_sets = {frozenset(s) for s in measurement_sets_by_run.values()}
    if len(distinct_measurement_sets) > 1:
        findings.append(
            Finding(
                "high",
                "leakage",
                "the set of measurement_type channels present differs "
                "across runs — measurement availability itself could "
                "predict class",
            )
        )
        notes["measurement_availability"] = "varies — see finding"
    else:
        notes["measurement_availability"] = (
            "identical measurement channel set for every run — no availability leakage"
        )

    # 11. fault-start policy across fault classes
    fault_starts_by_class: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["fault_start_sim_seconds"] is not None:
            fault_starts_by_class[row["class_label"]].append(
                row["fault_start_sim_seconds"]
            )
    ranges = {
        cls: (min(values), max(values))
        for cls, values in fault_starts_by_class.items()
        if values
    }
    non_overlapping: list[str] = []
    for cls_a, (min_a, max_a) in ranges.items():
        for cls_b, (min_b, max_b) in ranges.items():
            if cls_a >= cls_b:
                continue
            if max_a < min_b or max_b < min_a:
                non_overlapping.append(f"{cls_a} vs {cls_b}")
    if non_overlapping:
        findings.append(
            Finding(
                "medium",
                "leakage",
                "generation-policy leakage: some fault classes have "
                "non-overlapping fault_start_sim_seconds ranges, so fault "
                "timing alone could partially predict which fault class a "
                "run belongs to",
                evidence={"non_overlapping_pairs": non_overlapping, "ranges": ranges},
            )
        )
        notes["fault_start_policy"] = "non-overlapping ranges — see finding"
    else:
        notes["fault_start_policy"] = (
            "fault_start_sim_seconds ranges overlap across every fault "
            "class — timing alone does not trivially separate fault classes"
        )

    return findings, notes


def build_feature_exclusion_list() -> list[str]:
    """The section-8-mandated "future feature-exclusion list" for `runs.parquet`."""
    return list(ALWAYS_EXCLUDE_FROM_FEATURES)

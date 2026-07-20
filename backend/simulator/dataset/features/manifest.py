"""`feature_manifest.json` construction (PR167 spec section 10).

Must only be called after every output file it hashes has already been
written, mirroring `backend.simulator.dataset.manifest`'s ordering
convention — `generate.generate_features` enforces this.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.simulator.dataset.audit.loader import DatasetHandle
from backend.simulator.dataset.features.builder import FeatureTable
from backend.simulator.dataset.features.config import (
    DEFAULT_MEASUREMENTS,
    EXCLUDED_MEASUREMENTS,
    FEATURE_SCHEMA_VERSION,
    WINDOW_SECONDS,
)
from backend.simulator.dataset.features.exclusions import FORBIDDEN_FEATURE_FIELDS
from backend.simulator.dataset.manifest import resolve_git_commit

GENERATOR_VERSION = "odis-feature-generator/1.0"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_manifest_entries(files: tuple[Path, ...]) -> list[dict[str, Any]]:
    return [
        {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        for path in files
    ]


def _null_counts(table: Any, columns: tuple[str, ...]) -> dict[str, int]:
    return {name: table.column(name).null_count for name in columns}


def _rejection_counts(rejections_table: Any) -> tuple[dict[str, int], dict[str, int]]:
    """`(counts_by_reason, counts_by_feature)` — a rejected row can carry
    more than one reason/feature, so both are counted per-occurrence, not
    per-row."""
    by_reason: Counter[str] = Counter()
    by_feature: Counter[str] = Counter()
    for row in rejections_table.to_pylist():
        by_reason.update(row["reason_codes"])
        by_feature.update(row["invalid_feature_names"])
    return dict(sorted(by_reason.items())), dict(sorted(by_feature.items()))


def build_feature_manifest(
    *,
    handle: DatasetHandle,
    feature_table: FeatureTable,
    efficiency_clamp_stats: dict[str, Any],
    files: tuple[Path, ...],
    generation_command: str,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    git_commit, git_status = resolve_git_commit()

    label_rows = feature_table.labels.to_pylist()
    class_distribution = Counter(row["class_label"] for row in label_rows)
    split_counts = Counter(row["split"] for row in label_rows)
    rejection_counts_by_reason, rejection_counts_by_feature = _rejection_counts(
        feature_table.rejections
    )

    source_manifest_path = handle.directory / "dataset_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text())

    return {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "created_at": (created_at or datetime.now(UTC)).isoformat(),
        "generator_version": GENERATOR_VERSION,
        "git_commit": git_commit,
        "git_commit_status": git_status,
        "source_dataset": {
            "dataset_id": handle.spec.dataset_id,
            "directory": str(handle.directory),
            "manifest_sha256": _sha256_file(source_manifest_path),
            "manifest_created_at": source_manifest.get("created_at"),
            "manifest_generation_command": source_manifest.get("generation_command"),
        },
        "window_definitions": {
            "dt_seconds": 10.0,
            "window_seconds": list(WINDOW_SECONDS),
            "window_samples": [int(w / 10.0) for w in WINDOW_SECONDS],
            "trailing_convention": (
                "current_timestamp - window_seconds < observation_timestamp "
                "<= current_timestamp"
            ),
            "first_eligible_elapsed_sim_seconds": max(WINDOW_SECONDS),
        },
        "selected_measurements": list(DEFAULT_MEASUREMENTS),
        "excluded_measurements": {
            "names": list(EXCLUDED_MEASUREMENTS),
            "reason": "clamped/near-degenerate at this dataset's operating points",
            "evidence": efficiency_clamp_stats,
        },
        "feature_columns": list(feature_table.feature_columns),
        "metadata_columns": list(feature_table.metadata_columns),
        "excluded_fields": sorted(FORBIDDEN_FEATURE_FIELDS),
        "row_counts": {
            "total_rows_before_warmup_drop": (
                feature_table.total_rows_before_warmup_drop
            ),
            "dropped_warmup_rows": feature_table.dropped_warmup_rows,
            "eligible_rows": feature_table.eligible_rows,
            "valid_rows": feature_table.valid_rows,
            "rejected_rows": feature_table.rejected_rows,
        },
        "rejection_rate": (
            feature_table.rejected_rows / feature_table.eligible_rows
            if feature_table.eligible_rows > 0
            else 0.0
        ),
        "rejection_counts_by_reason": rejection_counts_by_reason,
        "rejection_counts_by_feature": rejection_counts_by_feature,
        "split_counts": dict(sorted(split_counts.items())),
        "class_distribution": dict(sorted(class_distribution.items())),
        "null_counts": {
            "features": _null_counts(
                feature_table.features, feature_table.feature_columns
            ),
            "labels": _null_counts(
                feature_table.labels,
                ("split", "class_label", "is_anomalous", "fault_severity"),
            ),
        },
        "files": _file_manifest_entries(files),
        "generation_command": generation_command,
    }

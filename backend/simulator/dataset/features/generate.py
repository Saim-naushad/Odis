"""Generates `features.parquet` + `labels.parquet` + manifest + dictionary
from an already-generated dataset (PR167 spec section 10).

Output lifecycle mirrors `backend.simulator.dataset.generate`: everything
is written to a fresh temporary directory next to the requested output
directory, and only atomically renamed into place once every file
(`feature_manifest.json` written last) has been produced successfully.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq

from backend.simulator.dataset.audit.loader import load_dataset
from backend.simulator.dataset.audit.records import build_records
from backend.simulator.dataset.features.builder import build_feature_table
from backend.simulator.dataset.features.diagnostics import efficiency_clamp_stats
from backend.simulator.dataset.features.feature_dictionary import (
    render_feature_dictionary,
)
from backend.simulator.dataset.features.manifest import build_feature_manifest


class FeatureOutputExistsError(Exception):
    """The requested output directory already exists and is non-empty."""

    def __init__(self, path: Path) -> None:
        super().__init__(
            f"output directory already exists and is non-empty: {path} "
            "(pass --overwrite / overwrite=True to replace it)"
        )
        self.path = path


@dataclass(frozen=True)
class GenerationResult:
    output_directory: Path
    feature_count: int
    total_rows_before_warmup_drop: int
    dropped_warmup_rows: int
    eligible_rows: int
    split_counts: dict[str, int]
    class_distribution: dict[str, int]


def generate_features(
    dataset_directory: Path,
    output_directory: Path,
    *,
    overwrite: bool = False,
    generation_command: str = "backend.simulator.dataset.features",
) -> GenerationResult:
    if output_directory.exists() and any(output_directory.iterdir()) and not overwrite:
        raise FeatureOutputExistsError(output_directory)

    handle = load_dataset(dataset_directory)
    records = build_records(handle)
    feature_table = build_feature_table(handle, records)

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )

    try:
        features_path = tmp_dir / "features.parquet"
        labels_path = tmp_dir / "labels.parquet"
        pq.write_table(feature_table.features, features_path)
        pq.write_table(feature_table.labels, labels_path)

        clamp_stats = efficiency_clamp_stats(records.telemetry, feature_table.features)

        dictionary_path = tmp_dir / "feature_dictionary.md"
        dictionary_path.write_text(render_feature_dictionary(clamp_stats))

        manifest = build_feature_manifest(
            handle=handle,
            feature_table=feature_table,
            efficiency_clamp_stats=clamp_stats,
            files=(features_path, labels_path, dictionary_path),
            generation_command=generation_command,
        )
        manifest_path = tmp_dir / "feature_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    if output_directory.exists():
        shutil.rmtree(output_directory)
    tmp_dir.rename(output_directory)

    label_rows = feature_table.labels.to_pylist()
    split_counts = dict(Counter(row["split"] for row in label_rows))
    class_distribution = dict(Counter(row["class_label"] for row in label_rows))

    return GenerationResult(
        output_directory=output_directory,
        feature_count=len(feature_table.feature_columns),
        total_rows_before_warmup_drop=feature_table.total_rows_before_warmup_drop,
        dropped_warmup_rows=feature_table.dropped_warmup_rows,
        eligible_rows=feature_table.eligible_rows,
        split_counts=split_counts,
        class_distribution=class_distribution,
    )

"""Reads one generated dataset directory into memory for auditing.

Deliberately thin: it only parses the files `generate.generate_dataset`
itself produces (`dataset_manifest.json`, `splits.json`, and the three
Parquet tables) and reconstructs the `DatasetSpec` that generated them from
the manifest's embedded `dataset_spec` — the same JSON shape
`DatasetSpec.to_json_dict`/`from_json_dict` round-trip elsewhere in this
package. Every check module downstream re-derives its own "expected" values
from this `spec` (via `run_plan.plan_runs` / `splits.assign_splits`) rather
than hand-coding expectations, so the audit stays correct if the generator's
policy ever changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from backend.simulator.dataset.dataset_spec import DatasetSpec

REQUIRED_FILES = (
    "dataset_manifest.json",
    "splits.json",
    "telemetry.parquet",
    "ground_truth.parquet",
    "runs.parquet",
)


class DatasetNotFoundError(Exception):
    """One or more required dataset files are missing from the directory."""

    def __init__(self, directory: Path, missing: tuple[str, ...]) -> None:
        super().__init__(
            f"{directory} is missing required dataset file(s): {', '.join(missing)}"
        )
        self.directory = directory
        self.missing = missing


@dataclass(frozen=True)
class DatasetHandle:
    """Everything an audit check needs, read once and held in memory.

    The pilot dataset (64 runs, ~185k telemetry rows) is small enough that
    holding all three tables in memory is simpler and more auditable than a
    streaming/chunked reader — see CONTRIBUTING.md's "avoid complexity
    before repeated patterns justify it."
    """

    directory: Path
    manifest: dict[str, Any]
    splits: dict[str, Any]
    spec: DatasetSpec
    runs: pa.Table
    telemetry: pa.Table
    ground_truth: pa.Table


def load_dataset(directory: Path) -> DatasetHandle:
    missing = tuple(
        name for name in REQUIRED_FILES if not (directory / name).is_file()
    )
    if missing:
        raise DatasetNotFoundError(directory, missing)

    manifest = json.loads((directory / "dataset_manifest.json").read_text())
    splits = json.loads((directory / "splits.json").read_text())
    spec = DatasetSpec.from_json_dict(manifest["dataset_spec"])

    return DatasetHandle(
        directory=directory,
        manifest=manifest,
        splits=splits,
        spec=spec,
        runs=pq.read_table(directory / "runs.parquet"),
        telemetry=pq.read_table(directory / "telemetry.parquet"),
        ground_truth=pq.read_table(directory / "ground_truth.parquet"),
    )

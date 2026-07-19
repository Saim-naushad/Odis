"""Materializes the three Parquet tables as plain Python records, once.

Every check module downstream (`structural`, `labels`, `variation`,
`physical`, `separability`, `leakage`) operates on these plain
`dict`/`list` records rather than re-deriving them from `pa.Table` — the
pilot dataset (64 runs) is small enough (~185k telemetry rows) that one
`to_pylist()` pass per table is cheap, and plain Python dicts make every
check's logic auditable without pyarrow compute-expression knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.simulator.dataset.audit.loader import DatasetHandle


@dataclass(frozen=True)
class DatasetRecords:
    runs: list[dict[str, Any]]
    telemetry: list[dict[str, Any]]
    ground_truth: list[dict[str, Any]]


def build_records(handle: DatasetHandle) -> DatasetRecords:
    return DatasetRecords(
        runs=handle.runs.to_pylist(),
        telemetry=handle.telemetry.to_pylist(),
        ground_truth=handle.ground_truth.to_pylist(),
    )

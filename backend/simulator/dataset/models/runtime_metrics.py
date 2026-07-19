"""Training/inference timing and artifact size (PR168 spec section 7,
"Runtime" metrics group).

Timing is measured directly around the exact calls `experiment.py` makes
for the selected pipeline — no separate synthetic microbenchmark harness.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.pipeline import Pipeline


@dataclass(frozen=True)
class RuntimeMetrics:
    training_seconds: float
    mean_prediction_latency_ms: float
    p95_prediction_latency_ms: float
    artifact_size_bytes: int

    def to_json_dict(self) -> dict[str, float | int]:
        return {
            "training_seconds": self.training_seconds,
            "mean_prediction_latency_ms": self.mean_prediction_latency_ms,
            "p95_prediction_latency_ms": self.p95_prediction_latency_ms,
            "artifact_size_bytes": self.artifact_size_bytes,
        }


def measure_per_row_prediction_latency_ms(
    pipeline: Pipeline, x: np.ndarray, *, max_rows: int = 500
) -> tuple[float, float]:
    """Mean and p95 single-row prediction latency in milliseconds.

    Calls `.predict` once per row (not once for the whole batch) since the
    spec asks for *per-row* latency — the operationally relevant number for
    a streaming inference path, even though batching would be faster.
    Capped at `max_rows` samples (evenly subsampled) so this stays fast on
    a 5k-row test split without changing what is measured.
    """
    n = x.shape[0]
    if n == 0:
        return 0.0, 0.0
    if n > max_rows:
        sample_indices = np.linspace(0, n - 1, max_rows).astype(int)
        x = x[sample_indices]
        n = max_rows

    durations_ms = np.empty(n, dtype=np.float64)
    for i in range(n):
        row = x[i : i + 1]
        start = time.perf_counter()
        pipeline.predict(row)
        durations_ms[i] = (time.perf_counter() - start) * 1000.0
    return float(durations_ms.mean()), float(np.percentile(durations_ms, 95))


def artifact_size_bytes(path: Path) -> int:
    return path.stat().st_size

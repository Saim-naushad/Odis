"""Leakage-safe, run-aware time-series feature foundation (PR167).

Transforms an already-generated dataset's `telemetry.parquet` +
`ground_truth.parquet` into `features.parquet` + `labels.parquet` — one row
per `(simulation_run_id, asset_id, timestamp)`, trailing windows only (30s/
60s/120s), a small high-value statistic set (mean/std/min/max/slope/delta),
two physically-interpretable cross-signal ratios, and four fixed-reference
physics-informed residuals. See `docs/` (once added) and
`feature_dictionary.md` (generated per output) for the full contract.

CLI usage::

    python -m backend.simulator.dataset.features \\
        --dataset datasets/pem-faults-pilot \\
        --output datasets/pem-faults-pilot-features

Requires the `dataset` optional dependency group (`pyarrow`).
"""

from __future__ import annotations

from backend.simulator.dataset.features.generate import (
    GenerationResult,
    generate_features,
)

__all__ = ["GenerationResult", "generate_features"]

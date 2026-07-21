"""PR176 runtime inference boundary for the PR175-promoted fault-diagnosis
system.

Loads a promoted model+alert-policy bundle once (`loader.
load_promoted_fault_system`), accepts canonical observable telemetry for
one asset over time (`telemetry.TelemetrySample`), and produces a typed,
explainable `result.InferenceResult` per timestamp
(`session.FaultInferenceSession`) — using the exact same feature formulas
as the offline PR167/PR173 pipeline (`backend.simulator.dataset.features.
row.compute_feature_row`), never an approximate streaming reimplementation.

This package has no dependency on dataset Parquet files, no Kafka
consumer/producer, no FastAPI route, and no database persistence — it is
the stable boundary future product-integration work will call, not that
integration itself. See `docs/runtime-inference.md`.
"""

from __future__ import annotations

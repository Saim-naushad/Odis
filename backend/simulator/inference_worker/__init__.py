"""Kafka streaming fault-inference worker (PR177).

Consumes canonical Plant Alpha telemetry from Kafka, assembles per-asset
per-timestamp samples, runs the PR176-promoted fault model incrementally
via `backend.simulator.inference.session.FaultInferenceManager`, and
publishes versioned diagnosis (`fault_inference.v1`) and alert-transition
(`fault_alert_transition.v1`) events for a future deterministic-reasoning
consumer (PR178).

Deliberately out of scope here: deterministic-reasoning integration,
recommendation generation, FastAPI endpoints, database persistence,
dashboard UI, model retraining/calibration, MLflow/model registry,
cross-process inference-state persistence, automatic model reload, and
autonomous plant control. See `docs/kafka-fault-inference-worker.md`.
"""

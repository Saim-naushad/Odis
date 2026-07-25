# ODIS Documentation

Entry point for all project documentation. Each link goes to a dedicated guide — this page is navigation only.

## Screenshots

Portfolio assets for the monitoring dashboard live in [`assets/`](assets/).

| Image | Description |
|-------|-------------|
| [dashboard-overview.png](assets/dashboard-overview.png) | Live four-stack fleet overview |
| [dashboard-ai-fault-diagnosis.png](assets/dashboard-ai-fault-diagnosis.png) | AI candidate fault with deterministic corroboration |
| [dashboard-model-provenance.png](assets/dashboard-model-provenance.png) | Model, policy, feature-schema, and source-event provenance |
| [dashboard-investigation-lifecycle.png](assets/dashboard-investigation-lifecycle.png) | Operator investigation lifecycle and attributed transition |
| [dashboard-investigation-timeline.png](assets/dashboard-investigation-timeline.png) | Selectable reasoning and AI-fault event history |
| [dashboard-incident.png](assets/dashboard-incident.png) | Live investigation during an active incident |

The final silent portfolio walkthrough is
[odis-v1.1-demo-final.mp4](assets/odis-v1.1-demo-final.mp4). The accepted
capture inventory and historical recapture criteria are documented in the
[Screenshot Checklist](release/screenshot-checklist.md).

## Getting Started

| Document | Description |
|----------|-------------|
| [README](../README.md) | Project overview, quick start, and repository map |
| [Quickstart](quickstart.md) | Install, run demos, and write your first reasoning program |
| [Contributing](../CONTRIBUTING.md) | Development setup, quality checks, and pull request guidelines |

## Architecture

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | Reasoning engine layers, components, and design principles |
| [Reasoning Pipeline](reasoning-pipeline.md) | Stage-by-stage flow from observation to recommendation |
| [Architecture Diagrams](architecture-diagrams.md) | Mermaid diagrams of the current implementation |

## Platform

| Document | Description |
|----------|-------------|
| [Platform Documentation](platform/README.md) | Index of deployment and operations guides |
| [Platform Architecture](platform/platform-architecture.md) | Production system design — API, worker, persistence, dashboard |
| [Docker Runtime](platform/docker-runtime.md) | Compose topology, networking, and local development |
| [Demo Environment](platform/demo-environment.md) | Plant Alpha simulator, MQTT path, and dashboard walkthrough |
| [TimescaleDB Foundation](platform/timescaledb-foundation.md) | Telemetry hypertables and time-series data model |
| [Historical Telemetry APIs](platform/telemetry-history.md) | Telemetry query flow and operator-facing history endpoints |
| [Continuous Aggregates](platform/continuous-aggregates.md) | Pre-computed rollups and aggregate APIs |
| [Telemetry Forecasting](platform/telemetry-forecasting.md) | ONNX-based forecast integration |
| [Kubernetes Deployment](platform/kubernetes-deployment.md) | K8s manifests, networking, and operations |
| [CI/CD and Container Registry](platform/ci-cd.md) | GitHub Actions validation and GHCR image publishing |
| [Business Metrics](platform/business-metrics.md) | Platform business and operational metrics |

## AI Fault Diagnosis (v1.1)

The promoted fault-inference model and its supporting decision layer, in build order.
Start with [AI Methodology](ai-methodology.md) for the end-to-end summary and final
results; the rest are the detailed pages it links to.

| Document | Description |
|----------|-------------|
| [AI Methodology](ai-methodology.md) | End-to-end summary: dataset → features → models → calibration → alert policy → OOD → robustness → promotion → runtime |
| [Simulator Dataset Generation](simulator-dataset-generation.md) | Versioned, offline Parquet dataset generation from Plant Alpha |
| [Dataset Quality Audit](dataset-quality-audit.md) | Pilot-dataset quality report and leakage checks |
| [Numerically Safe Features](numerically-safe-features.md) | Numerical-safety hardening on the feature pipeline |
| [Baseline Fault Diagnosis Models](baseline-fault-diagnosis-models.md) | Leakage-safe baseline model evaluation |
| [Calibrated Confidence and Alert Policy](calibrated-confidence-and-alert-policy.md) | Calibration experiment and its regression finding |
| [Uncalibrated Temporal Alert Policy](uncalibrated-temporal-alert-policy.md) | The deterministic hysteresis policy actually promoted (entry/exit persistence) |
| [Out-of-Distribution Evaluation](out-of-distribution-evaluation.md) | Fixed-policy stress test under distribution shift |
| [Isolated Shift Evaluation](isolated-shift-evaluation.md) | Per-shift diagnosis isolating which regime broke the model |
| [Robustness Training](robustness-training.md) | Broader-regime retraining and promotion criteria for the current model |
| [Runtime Inference](runtime-inference.md) | The runtime boundary between offline training and streaming inference |
| [Kafka Fault Inference Worker](kafka-fault-inference-worker.md) | Streaming worker: Kafka telemetry → assembled samples → promoted model → alerts |
| [Reasoning Bridge](reasoning-bridge.md) | Confirmed AI fault alerts → deterministic corroboration and recommendation |
| [Fault Investigation Dashboard](fault-investigation-dashboard.md) | Operator-facing API, SSE, and dashboard integration for AI-detected faults |

## Reasoning Engine

| Document | Description |
|----------|-------------|
| [Fuel Cell Profile](profiles/fuel_cell_profile.md) | Domain profile configuration for PEM fuel-cell scenarios |

## Simulator

| Document | Description |
|----------|-------------|
| [Simulator](simulator.md) | Plant Alpha simulator internals, scenarios, and publish cadence |

## Release

| Document | Description |
|----------|-------------|
| [Release Notes](../RELEASE_NOTES.md) | v1.1.0 and v1.0.0 summaries by subsystem |
| [v1.1 Release Scorecard](release/v1.1-scorecard.md) | Hardening-pass audit findings, fixes, live validation, and final verdict |
| [Benchmarking Methodology](benchmarking.md) | `scripts/benchmark_odis` design — scenarios, isolation, measurement contracts |
| [v1.1 Performance Report](release/v1.1-performance-report.md) | Measured throughput, latency, and reliability results up to 100 simulated assets |
| [v1.1 Benchmark Evidence](release/v1.1-benchmark-evidence/README.md) | Raw per-run evidence (environment, metrics, reports) backing the performance report |
| [Portfolio Summary](release/portfolio-summary.md) | Resume bullets and interview explanations for this release |
| [Screenshot Checklist](release/screenshot-checklist.md) | Accepted portfolio assets and historical recapture criteria |
| [Demo Script](release/demo-script.md) | Superseded long-form narrated walkthrough, retained for historical context |

## Research

Conceptual and forward-looking documents. Not all concepts are fully implemented.

| Document | Description |
|----------|-------------|
| [Operational Reasoning Model](research/operational-reasoning-model.md) | Theoretical foundations of operational reasoning |
| [Operational Context](research/operational-context.md) | Context modeling for assessments and decisions |
| [Expectation-Based Reasoning](research/expectation-based-reasoning.md) | Expectation evaluation and deviation detection |
| [Fuel Cell Operational Knowledge](research/fuel-cell-operational-knowledge.md) | Domain knowledge for PEM fuel-cell operations |

## RFCs

Accepted architectural decisions and design history.

| Document | Description |
|----------|-------------|
| [RFC-0001: Core Operational Reasoning Architecture](rfcs/RFC-0001-core-operational-reasoning-architecture.md) | Domain model, layering, and reasoning boundaries |
| [RFC-0002: Multi-Signal Reasoning](rfcs/RFC-0002-multi-signal-reasoning.md) | Trend + variation signal design |

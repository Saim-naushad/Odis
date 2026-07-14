# ODIS Documentation

Entry point for all project documentation. Each link goes to a dedicated guide — this page is navigation only.

## Screenshots

Portfolio assets for the monitoring dashboard live in [`assets/`](assets/).

| Image | Description |
|-------|-------------|
| [dashboard-overview.png](assets/dashboard-overview.png) | Fleet overview during an active cooling degradation incident |
| [dashboard-telemetry.png](assets/dashboard-telemetry.png) | Telemetry correlated with operational reasoning |
| [dashboard-investigation.png](assets/dashboard-investigation.png) | Reasoning timeline from evidence to recommendation |

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
| [Release Notes](../RELEASE_NOTES.md) | v1.0.0 summary by subsystem |
| [Screenshot Checklist](release/screenshot-checklist.md) | Shot list for portfolio and release screenshots |
| [Demo Script](release/demo-script.md) | 3–5 minute narrated recording script |

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

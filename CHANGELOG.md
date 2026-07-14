# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-14

Everything below has shipped on top of the 0.1.0 reasoning library: a full
deployable platform (backend, worker, dashboard, simulator) and deeper
reasoning-engine capabilities. Grouped by area; not every commit is listed.

### Added — Reasoning engine
- Cross-measurement relationship analysis (correlation and contradiction detection) feeding structured assessments
- Operational context, expectation domain model, and profile-driven expectation evaluation
- `OperationalProfile` extension point with a fuel-cell profile demonstrating domain-specific reasoning without core pipeline changes
- Operational state and hypothesis models with deterministic hypothesis refinement
- Reasoning execution trace attached to each result for step-by-step explainability

### Added — Platform (backend)
- FastAPI + PostgreSQL/TimescaleDB persistence foundation with a background reasoning worker
- REST ingestion (`POST /observations`) that triggers reasoning automatically via a durable job queue
- MQTT ingestion bridge (Mosquitto → mqtt-bridge → API) with durable QoS acknowledgment
- Monitoring API: reasoning history, timeline, recommendations, notifications, and a composed digital twin read model
- Operator investigation lifecycle (acknowledged → investigating → resolved) with append-only transition records
- TimescaleDB continuous aggregates and historical telemetry query APIs
- ONNX-based telemetry forecasting as an operator-facing analytics path, isolated from core reasoning
- Redis-backed digital twin caching with event-driven invalidation
- Kafka integration events via a transactional outbox for at-least-once delivery
- Server-Sent Events endpoint (`/monitoring/events`) for real-time dashboard updates
- Structured logging, request ID correlation, OpenTelemetry tracing, Prometheus metrics, and business metrics
- Health and readiness endpoints, worker heartbeat, and distributed runtime readiness checks

### Added — Frontend
- React 19 + TypeScript + Vite operator monitoring dashboard (fleet view, telemetry, recommendations, investigation timeline)
- React Query state management with SSE-driven cache invalidation and a 60s poll fallback
- Interactive telemetry visualization and operator investigation actions from the dashboard

### Added — Simulator and operations
- Plant Alpha: a deterministic, physics-based 4-stack PEM fuel-cell simulator (first-order-lag model, not RNG) with fault and recovery scenarios
- End-to-end demo environment (simulator → MQTT → API → worker → dashboard) with reproducible, scripted demo scenarios
- Docker Compose multi-service runtime and Kubernetes deployment manifests
- GitHub Actions CI (backend, frontend, Docker image builds/publish to GHCR)

## [0.1.0] - 2026-07-07
### Added
- Operational reasoning pipeline (evidence → signal → assessment → plan)
- Multi-signal reasoning (trend + variation signals)
- Replay and history (append-only reasoning records and summaries)
- Operational analytics and summary views for runs
- Attention queue for prioritizing operational focus
- Observation sources, including CSV ingestion
- CLI and runnable examples
- Documentation and a public `odis` import surface


# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Three fixes found and root-caused during a pre-recording live audit of the
v1.1 dashboard, verified against a rebuilt live stack (not just unit tests).

### Fixed
- **Fleet-state / notification contradiction**: elevated risk alone
  (`risk_level == HIGH`, a leading indicator ahead of a confirmed CRITICAL
  health reading) could mint the same CRITICAL-severity, "Immediate
  mitigation required" notification as a confirmed CRITICAL health reading —
  visible on the dashboard as a CRITICAL banner over an otherwise-NORMAL,
  LOW-risk fleet with no explanation. Root cause was three stacked issues:
  `VariationDetector` had no minimum-sample gate (unlike its sibling
  `TrendDetector`), letting a 2-sample window trip the HIGH-variation
  threshold from ordinary load-cycling noise within seconds of a clean
  start; the same variation signal was then scored twice in the health
  formula (`priority_penalty` and `assessment_penalty`); and
  `RecommendationEngine`/`NotificationPolicyEngine` collapsed the
  CRITICAL/elevated-risk distinction into one severity tier. Fixed by
  gating the detector, removing the double-count, and splitting
  recommendations into P0 (confirmed CRITICAL → CRITICAL severity,
  "Immediate mitigation required") and P1 (elevated risk only → WARNING
  severity, "Elevated risk identified"). The dashboard's alert banner also
  now explicitly names the asset's current health status whenever a
  still-open notification (notifications are an intentional append-only
  log) implies worse than current reality, instead of leaving the two facts
  side by side unexplained.
- **Operator investigation lifecycle reliability**: `recommendation_id` was
  derived from the reasoning run's own timestamp, so it changed on every
  reasoning cycle (roughly every 4 seconds) even when the recommendation's
  content hadn't materially changed. Because Acknowledge/Start
  investigating/Resolve are keyed to `recommendation_id`, a transition
  request frequently 404'd against an already-superseded id, and reaching
  RESOLVED reliably required racing 15-20+ retries. Fixed by deriving the
  id from the recommendation's own material classification (asset, category,
  priority, urgency, title) instead of a timestamp, so it stays stable
  across cycles until the recommendation actually changes. No frontend
  retry logic was added — the identity itself was the fix. Live-verified:
  the full `NEW → ACKNOWLEDGED → INVESTIGATING → RESOLVED` sequence now
  completes on the first click for every transition.
- **AI-fault timeline events were not selectable**: `ai_fault_*` timeline
  events (alert received, corroboration completed, investigation updated,
  recommendation recorded, alert cleared) already carried an
  `investigation_id`, and the detail endpoint already existed, but the
  Timeline component only recognized `run_id`-bearing events as clickable.
  Selecting one now shows the associated AI fault investigation in Event
  Context — never a fabricated reasoning-run relationship. Known
  limitation, unchanged by this fix: the timeline preview shows only 5
  recent events, and high-frequency observation events can crowd an
  `ai_fault_*` event out of that window, so one is selectable when visible
  but not guaranteed to be visible at any given moment.

## [1.1.0] - 2026-07-22

Adds a promoted AI-assisted fault-diagnosis capability on top of v1.0's
deterministic platform, with deterministic reasoning kept as the sole
decision authority. Grouped by area; not every commit is listed. See
[AI Methodology](docs/ai-methodology.md) for the full dataset-to-promotion
narrative and [Release Scorecard](docs/release/v1.1-scorecard.md) for the
hardening-pass audit.

### Added — Dataset and model (offline)
- Versioned, offline Parquet dataset generation from Plant Alpha with a pilot quality/leakage audit
- Numerically-safe, leakage-safe time-series feature pipeline with explicit insufficient-data handling
- Leakage-safe baseline fault-diagnosis models (logistic regression, feature set D, `C=10.0`)
- Calibrated-confidence experiment — found and documented as a regression, not promoted
- A deterministic, uncalibrated temporal alert policy (entry probability 0.70 / persistence 4 samples, healthy exit 0.45 / persistence 2 samples) promoted instead
- Fixed-policy out-of-distribution evaluation and isolated per-shift diagnosis (high-load, hot-start, late-onset, high-noise, combined)
- Broader-regime robustness retraining and promotion criteria for the currently-promoted model (`plant_alpha_fault_v1`)

### Added — Streaming inference and reasoning bridge (runtime)
- Kafka fault-inference worker: consumes Plant Alpha telemetry, assembles bounded per-asset samples, runs the promoted model, publishes `fault_inference.v1` / `fault_alert_transition.v1`
- Deterministic 11-sample warm-up then first prediction at sample 12, matching the model's trained window exactly; in-memory only, resets on worker restart
- `kafka+http` simulator transport: one synchronized tick fans out to both Kafka and HTTP so corroboration data is provably the same telemetry that produced the alert
- Reasoning bridge worker: corroborates confirmed ML alerts against real observations using deterministic telemetry rules, never the model's own score, and produces a bounded, explainable recommendation
- Idempotent event processing end to end (deterministic UUIDv5 event IDs; Kafka replay does not duplicate evidence or investigations)
- Prometheus metrics for both new workers (31 series total) and a small set of demo/reference Prometheus alert rules

### Added — Operator-facing platform
- Active AI fault investigation API, investigation history/detail, and deterministic-rule provenance in every response
- Score caveats and an explicit authority-boundary note on every AI-assisted response (the model's score is never presented as a probability or as authoritative)
- Outbox → Redis → SSE invalidation wired to AI fault investigation updates, reusing the existing event-driven cache-invalidation path
- Dashboard: active fault investigation card, investigation history panel, and lifecycle states (clear / disagreement / insufficient-evidence)

### Fixed — v1.1 release hardening
- Outbox dispatcher: a failed Kafka publish no longer silently marks the event dispatched (it retried the Kafka leg on the next cycle instead of losing the event)
- Dashboard: a transient background-refresh error no longer hides an already-loaded fault investigation or its history (last-good state now stays visible, per the platform's stated durable-state guarantee)
- `docker compose --profile demo up` now actually exercises the AI-fault-alert pipeline (previously the demo's `mqtt`-only transport never fed the fault-inference worker's Kafka topic)
- Compose `DATABASE_URL`/Postgres credentials are now overridable via `.env` like every other setting, instead of hardcoded in a file labeled "production runtime"
- CI (`backend.yml`) now runs `pytest -m "not integration"`, matching `CONTRIBUTING.md`'s documented command, instead of a bare `pytest` that silently never ran the Postgres concurrency test

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


# ODIS v1.0.0

First tagged release. ODIS is a deterministic operational reasoning engine plus a
deployable platform (ingestion, persistence, worker, dashboard) demonstrated on a
physics-based PEM fuel-cell simulator. This release consolidates everything built
on top of the original 0.1.0 reasoning library into one versioned, demo-ready
system.

## Reasoning engine

- Seven-stage deterministic pipeline (`src/application/reasoning/`): Signal
  Extraction → Evidence Generation → Hypothesis → Assessment → Confidence →
  Explanation → Planning. No ML in the core path — every step is traceable from
  evidence to decision.
- Trend, variation, and cross-measurement correlation/contradiction detectors,
  feeding structured assessments.
- Operational context, expectation domain model, and profile-driven expectation
  evaluation — the default profile and a fuel-cell profile share the same
  detectors and planner.
- `OperationalProfile` extension point demonstrating domain-specific reasoning
  without touching core pipeline code.
- Append-only reasoning execution trace attached to every result for
  step-by-step explainability and replay.

## Event-driven architecture

- Transactional outbox (`OutboxDispatcher`) for at-least-once delivery of
  domain events to Kafka, decoupling persistence from downstream consumers.
- In-process `DomainEventBus` driving cache invalidation and timeline
  projections off the same events, rather than services reaching into each
  other directly.
- Server-Sent Events endpoint (`/monitoring/events`) pushing targeted React
  Query cache invalidation to the dashboard, with a 60s poll as a fallback only
  when SSE is disconnected.
- MQTT ingestion (Mosquitto → `mqtt-bridge` → `POST /observations`) with
  durable QoS acknowledgment, alongside direct HTTP ingestion.

## Digital twin platform

- `DigitalTwinService` composes a read model from `MonitoringService` output
  plus forecasts — it does not recompute operational state, only assembles it.
- Redis-backed caching with event-driven invalidation keyed off the same
  domain events that drive the dashboard's SSE stream.
- ONNX-based telemetry forecasting as an isolated, opt-in analytics path,
  kept out of the core reasoning pipeline by design.
- TimescaleDB continuous aggregates and historical telemetry query APIs for
  time-range queries over raw and rolled-up observations.

## Investigation workflow

- Operator investigation lifecycle (`ACKNOWLEDGED` → `INVESTIGATING` →
  `RESOLVED`) as append-only transition records keyed on the Recommendation,
  not the DecisionPlan — a recommendation with no transition is implicitly
  `NEW`.
- Investigation timeline is explainable: each entry carries interactive event
  context back to the evidence and assessment that produced it.
- Live status transitions surface on the dashboard via the same domain-event
  path used for cache invalidation, so operator actions reflect immediately
  without a manual refresh.

## Scheduler redesign

- Reasoning job queue redesigned around per-asset outstanding-job coalescing:
  at most one job per asset may be `PENDING` or `RUNNING` at a time, enforced
  by a partial unique index.
- A `dirty` flag records that an observation arrived while a job was already
  outstanding, guaranteeing exactly one follow-up job is scheduled on
  completion or failure instead of one job per observation.
- `coalesced_count` tracks how many enqueue requests were absorbed into a
  single job, giving worker metrics direct visibility into coalescing
  effectiveness under load.
- Concurrency-tested against overlapping enqueue/dequeue/complete races (see
  `tests/backend/test_reasoning_job_scheduler_concurrency.py`).

## Frontend dashboard

- React 19 + TypeScript + Vite single-page operator console — fleet view,
  telemetry visualization, recommendations, and investigation timeline
  composed from `components/monitoring/*`.
- State managed entirely through React Query with SSE-driven invalidation;
  no client-side polling loop competing with real-time updates.
- Interactive telemetry charts with time-range and resolution controls,
  correlated with the investigation panel for the same asset.
- Dashboard polished for demo readiness: consistent loading and empty states,
  asset catalog metadata for the four Plant Alpha stacks, and stabilized
  real-time update behavior (no invalidation churn during live sessions).

## Simulator

- Plant Alpha: a deterministic, physics-based 4-stack PEM fuel-cell simulator
  using a first-order-lag model — not RNG — so subsystems move coherently
  under fault scenarios.
- Scripted, reproducible scenarios (cooling degradation, hydrogen supply
  issue, sensor anomaly, recovery) plus a `demo_presentation` script that
  drives a ~6:40 narrated walkthrough (baseline → cooling degradation →
  warning/critical → recovery) with logged phase transitions as recording
  cues, and a long-form `demo_realistic` script for extended validation.
- Publishes over MQTT in the production path, or directly over HTTP for local
  development without the full Compose stack.
- Treated strictly as an external boundary: the simulator never writes to
  repositories directly.

## Documentation

- `docs/` restructured around entry points for architecture, platform
  operations, the reasoning pipeline, the simulator, and research/RFC
  material — start at `docs/README.md`.
- Demo environment guide with throughput benchmarks, queue-lag acceptance
  thresholds, a scripted recording procedure, and known scalability
  limitations stated explicitly rather than implied.
- `CONTRIBUTING.md` codifies the engineering principles that protect the
  reasoning core (explicit staging, append-only history, no premature
  abstraction) as the codebase grows.
- Repository-wide documentation pass for public release: consistent wording,
  working links, and portfolio-quality presentation.

## Known limitations

Carried forward from `README.md` — this release does not claim production
hardening:

- No auth, multi-tenancy, or SLA guarantees.
- Each reasoning job reloads full per-asset observation history; long demo
  sessions can grow queue depth without bounded reasoning windows.
- `DecisionPlanner` matches on assessment text (substring/casefold) as a
  known, intentional placeholder, not a production policy engine.
- Only trend and variation are first-class signal types; anomaly and
  rate-of-change are not yet separate detectors.
- Action and outcome records are persisted but not wired to external control
  systems (no closed-loop execution).
- No OPC UA or SCADA connectors — MQTT and HTTP ingestion only.

## Upgrading

This is the first tagged release; there is no prior version to migrate from.
See [`CHANGELOG.md`](CHANGELOG.md) for the full history, including the
underlying 0.1.0 reasoning-library baseline this platform was built on.

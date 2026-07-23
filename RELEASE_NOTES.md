# Unreleased

Three fixes from a pre-recording live audit of the v1.1 dashboard, each
root-caused and verified against a rebuilt live stack before being applied.

- **The dashboard could show a CRITICAL banner over an otherwise-healthy
  fleet.** Elevated risk — a leading indicator that can precede a confirmed
  CRITICAL health reading — was treated the same as a confirmed CRITICAL
  reading when generating operator notifications. The two are now
  distinguished explicitly: **P0** (confirmed CRITICAL health) shows a
  CRITICAL-severity "Immediate mitigation required" notification; **P1**
  (elevated risk, health not yet confirmed CRITICAL) shows a
  WARNING-severity "Elevated risk identified" notification instead.
  Notifications remain an intentional append-only record — one can still
  legitimately stay open after health recovers — but the dashboard now
  explains that distinction inline rather than showing two contradictory
  facts side by side.
- **The operator investigation workflow (Acknowledge → Start investigating →
  Resolve) could fail to complete.** The identifier a transition referenced
  changed on every reasoning cycle even when nothing about the underlying
  recommendation had materially changed, so a transition request could be
  rejected as stale seconds after the recommendation it targeted was shown
  on screen. The identifier is now stable across cycles until the
  recommendation's actual classification changes. The full lifecycle now
  completes reliably.
- **AI-detected fault events in the investigation timeline are now
  selectable.** Clicking one shows the associated AI fault investigation —
  diagnosis, corroboration, and recommendation — directly in the timeline's
  event detail panel. (The timeline only previews the 5 most recent events
  for an asset, so an AI-fault event isn't guaranteed to be visible at every
  moment — it's selectable whenever one is showing.)

---

# ODIS v1.1.0

Adds a promoted AI-assisted fault-diagnosis capability — trained on Plant Alpha
telemetry, evaluated under distribution shift, and wired into a streaming
inference path — while keeping v1.0's deterministic reasoning engine as the
sole decision authority. The model's job is to raise a candidate alert;
deterministic telemetry rules corroborate or reject it, and every operator-facing
response carries an explicit score caveat and authority-boundary note. See
[AI Methodology](docs/ai-methodology.md) for the full dataset-to-promotion
narrative and [Release Scorecard](docs/release/v1.1-scorecard.md) for this
release's hardening-pass audit and honest readiness verdict.

## Promoted AI system

- Model: logistic regression, feature set D, `C=10.0` — the best-performing
  leakage-safe baseline evaluated (see
  [Baseline Fault Diagnosis Models](docs/baseline-fault-diagnosis-models.md)).
  A calibrated-confidence variant was evaluated and found to regress alert
  quality; it was not promoted (see
  [Calibrated Confidence and Alert Policy](docs/calibrated-confidence-and-alert-policy.md)).
- Alert policy: deterministic hysteresis — entry probability 0.70 sustained
  for 4 samples, healthy exit at probability 0.45 sustained for 2 samples
  (see [Uncalibrated Temporal Alert Policy](docs/uncalibrated-temporal-alert-policy.md)).
- Evaluated on the original pilot distribution, a broader training
  distribution, and isolated high-load / hot-start / late-onset / high-noise
  / combined out-of-distribution shifts, with the model retrained once
  against the broader regime and re-promoted under documented criteria (see
  [Robustness Training](docs/robustness-training.md)).
- Runtime artifact bundle: `artifacts/models/plant_alpha_fault_v1/`, hash- and
  schema-verified by the fault-inference worker before it reports healthy.

## Streaming inference and reasoning bridge

- Kafka fault-inference worker: consumes Plant Alpha telemetry, assembles
  bounded per-asset samples, runs the promoted model, publishes
  `fault_inference.v1` / `fault_alert_transition.v1`. Warm-up is exactly
  11 samples then a first prediction at sample 12 (the model's trained
  window), held in memory only — a worker restart resets warm-up.
  See [Kafka Fault Inference Worker](docs/kafka-fault-inference-worker.md).
- Reasoning bridge worker: corroborates a confirmed ML alert against real
  observations using deterministic telemetry rules — never the model's own
  score — and produces a bounded recommendation or explicitly withholds one.
  See [Reasoning Bridge](docs/reasoning-bridge.md).
- Idempotent end to end: deterministic UUIDv5 event IDs mean Kafka replay
  does not duplicate evidence or investigations.
- Kafka and HTTP delivery are not one atomic transaction — see
  [Release Scorecard](docs/release/v1.1-scorecard.md)'s failure-mode matrix
  for exactly what is and isn't retried on partial failure.

## Operator-facing dashboard

- Active AI fault investigation API, investigation history/detail, and
  deterministic-rule provenance (rule IDs, corroboration result, supporting
  observations) in every response.
- Every AI-assisted response carries a score caveat ("uncalibrated diagnostic
  ranking, not a probability") and an authority-boundary note — the model is
  evidence, not a confirmed diagnosis.
- Outbox → Redis → SSE invalidation wired to AI fault investigation updates,
  reusing the same event-driven cache-invalidation path as v1.0.
- Dashboard: active fault investigation card, investigation history panel,
  and lifecycle states (clear / disagreement / insufficient-evidence). See
  [Fault Investigation Dashboard](docs/fault-investigation-dashboard.md).

## Important limitations

- Trained and evaluated entirely on simulator-generated data — no real-plant
  validation.
- The model's native score is an uncalibrated ranking, not a calibrated
  real-world probability; a calibration attempt regressed alert quality and
  was explicitly not promoted.
- Fault-inference warm-up state is in-memory only and resets on worker
  restart.
- Kafka and HTTP delivery are not a single atomic transaction (see the
  failure-mode matrix in the release scorecard).
- Deterministic reasoning remains the sole authority — no autonomous control,
  no closed-loop actuation.
- Evaluation cohorts are small (simulator-scale), not production traffic
  volumes.

## Upgrading from v1.0.0

No destructive migration; `alembic upgrade head` applies the v1.1 schema
additions (AI fault evidence/investigation tables, outbox) on top of a v1.0
database. See [Migration and Fresh Database](docs/release/v1.1-scorecard.md)
for the verified fresh-database and upgrade paths.

---

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

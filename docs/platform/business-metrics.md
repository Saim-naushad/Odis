# Business Observability Metrics

ODIS exposes Prometheus metrics at `GET /metrics`. Business metrics are defined in
`backend/app/infrastructure/metrics/` and instrumented through small helper functions
so application code never constructs Prometheus collectors directly.

Prometheus imports are confined to the metrics package. Domain and `src/` layers
remain free of observability dependencies.

## Architecture

```
backend/app/infrastructure/metrics/
├── registry.py                  # Central registry; side-effect imports register collectors
├── worker_metrics.py            # Reasoning job lifecycle
├── reasoning_metrics.py         # Reasoning runs, trend analysis, digital twin builds
├── operational_state_metrics.py # State transitions
├── recommendation_metrics.py    # Recommendation computation
├── notification_metrics.py      # Notification creation
├── integration_event_metrics.py # Per-type integration event publishing
├── observation_metrics.py       # Observation ingestion
├── cache_metrics.py             # Digital twin cache
├── http_metrics.py              # HTTP request instrumentation
└── monitoring_metrics.py        # SSE connection gauge
```

Each module exports:

1. Prometheus collector objects (used only inside the metrics package and tests).
2. `record_*()` helper functions called from application and infrastructure code.

## Metric Catalog

### Worker metrics (`worker_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `reasoning_jobs_created_total` | Counter | — | Jobs enqueued after observation ingestion | `DatabaseReasoningJobQueue.enqueue` |
| `reasoning_jobs_completed_total` | Counter | — | Jobs marked COMPLETED | `DatabaseReasoningJobQueue.complete` |
| `reasoning_jobs_failed_total` | Counter | — | Jobs marked FAILED | `DatabaseReasoningJobQueue.fail` |
| `reasoning_jobs_running` | Gauge | — | Jobs currently in RUNNING state | `DatabaseReasoningJobQueue.claim` (+1), `complete` / `fail` (−1) |
| `reasoning_job_duration_seconds` | Histogram | — | End-to-end worker processing time (claim → commit + outbox dispatch) | `ReasoningWorker.process_next` |

### Reasoning metrics (`reasoning_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `reasoning_runs_total` | Counter | — | Reasoning runs completed by the worker | `ReasoningWorker.process_next` |
| `reasoning_duration_seconds` | Histogram | — | `ReasoningSession.run` execution time | `ObservationService._run_reasoning_for_asset` |
| `reasoning_failures_total` | Counter | — | Reasoning runs that raised an exception in the worker | `ReasoningWorker.process_next` |
| `trend_analysis_duration_seconds` | Histogram | — | `analyze_trend_diagnostics` execution time | `ObservationService._run_reasoning_for_asset` (before and after reasoning) |
| `digital_twin_build_duration_seconds` | Histogram | — | Digital twin assembly on cache miss | `DigitalTwinService._assemble` |

### Operational state metrics (`operational_state_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `operational_state_transitions_total` | Counter | `from_state`, `to_state` | Health status or risk level changes during reasoning | `ObservationService._run_reasoning_for_asset` when `HealthChanged` or `RiskChanged` outbox events are created |

Label values use the domain enum strings (e.g. `CRITICAL`, `WARNING`, `HIGH`, `MEDIUM`).

### Recommendation metrics (`recommendation_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `recommendations_computed_total` | Counter | `category`, `priority`, `urgency` | Structured recommendations produced during reasoning | `ObservationService._run_reasoning_for_asset` after `RecommendationEngine.compute` |

### Notification metrics (`notification_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `notifications_created_total` | Counter | `severity`, `status` | New notifications emitted during reasoning | `ObservationService._run_reasoning_for_asset` when a `NotificationCreated` outbox event is created |

### Integration event metrics (`integration_event_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `integration_events_digital_twin_updated_total` | Counter | — | `DigitalTwinUpdated` events published to Kafka | `KafkaIntegrationEventPublisher.publish` |
| `integration_events_operational_state_changed_total` | Counter | — | `OperationalStateChanged` events published | `KafkaIntegrationEventPublisher.publish` |
| `integration_events_notification_raised_total` | Counter | — | `NotificationRaised` events published | `KafkaIntegrationEventPublisher.publish` |
| `integration_publish_failures_total` | Counter | — | Failed publish attempts (any type) | `KafkaIntegrationEventPublisher.publish` |

### Observation metrics (`observation_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `observations_created_total` | Counter | — | Observations persisted via the API | `ObservationService.create` |

### Infrastructure metrics (unchanged)

| Module | Key metrics |
|--------|-------------|
| `http_metrics.py` | `http_requests_total`, `http_request_duration_seconds`, `http_requests_in_progress` |
| `cache_metrics.py` | `cache_hits_total`, `cache_misses_total`, `cache_invalidations_total` |
| `monitoring_metrics.py` | `monitoring_sse_connections` |

## Emission map

```
POST /observations
  └─ record_observation_created()
  └─ record_reasoning_job_created()          [enqueue]

ReasoningWorker.process_next
  └─ record_reasoning_job_running_started()  [claim]
  └─ ObservationService._run_reasoning_for_asset
  │    ├─ record_trend_analysis_duration()   [×2]
  │    ├─ record_reasoning_duration()
  │    ├─ record_recommendation_computed()
  │    ├─ record_operational_state_transition() [health / risk changes]
  │    └─ record_notification_created()
  └─ record_reasoning_job_running_finished() [complete / fail]
  └─ record_reasoning_job_completed() | record_reasoning_job_failed()
  └─ record_reasoning_run() | record_reasoning_failure()
  └─ record_reasoning_job_duration()

GET /monitoring/assets/{id}/digital-twin  (cache miss)
  └─ record_digital_twin_build_duration()

OutboxDispatcher → KafkaIntegrationEventPublisher.publish
  └─ record_integration_event_published(type)
  └─ record_integration_publish_failure()    [on error]
```

## Query examples

```promql
# Job throughput
rate(reasoning_jobs_completed_total[5m])

# In-flight jobs
reasoning_jobs_running

# P95 reasoning session latency
histogram_quantile(0.95, rate(reasoning_duration_seconds_bucket[5m]))

# State transitions by destination
sum by (to_state) (rate(operational_state_transitions_total[1h]))

# Recommendations by priority
sum by (priority) (rate(recommendations_computed_total[1h]))

# Integration events by type
rate(integration_events_digital_twin_updated_total[5m])
rate(integration_events_operational_state_changed_total[5m])
rate(integration_events_notification_raised_total[5m])
```

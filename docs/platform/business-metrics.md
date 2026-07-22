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
├── reasoning_bridge_metrics.py  # AI-fault reasoning bridge worker (v1.1)
├── outbox_metrics.py            # Outbox dispatcher backlog (v1.1)
├── operational_state_metrics.py # State transitions
├── recommendation_metrics.py    # Recommendation computation
├── notification_metrics.py      # Notification creation
├── integration_event_metrics.py # Per-type integration event publishing
├── observation_metrics.py       # Observation ingestion
├── forecast_metrics.py          # ONNX telemetry forecast inference
├── health_metrics.py            # Worker heartbeat and readiness probe failures
├── mqtt_bridge_metrics.py       # MQTT ingestion bridge message flow
├── cache_metrics.py             # Digital twin cache
├── http_metrics.py              # HTTP request instrumentation
└── monitoring_metrics.py        # SSE connection gauge

backend/simulator/inference_worker/
└── metrics.py                   # Fault-inference worker (v1.1) — separate process,
                                  # separate /metrics endpoint (port 9108); does not
                                  # import backend.app.infrastructure.metrics
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

### Reasoning bridge metrics (`reasoning_bridge_metrics.py`, v1.1)

The reasoning bridge worker consumes `fault_alert_transition.v1` events and produces
deterministic AI-fault investigations. Exposed on the same `/metrics` endpoint as the
API process. See [Reasoning Bridge](../reasoning-bridge.md).

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `reasoning_bridge_alert_transitions_consumed_total` | Counter | — | Alert-transition events consumed |
| `reasoning_bridge_malformed_events_total` | Counter | `reason` | Events rejected as malformed |
| `reasoning_bridge_duplicate_events_ignored_total` | Counter | — | Replays ignored as already-processed |
| `reasoning_bridge_corroboration_results_total` | Counter | `result` | Corroboration outcomes (e.g. `confirmed`, `not_corroborated`, `insufficient_evidence`) |
| `reasoning_bridge_investigations_created_total` | Counter | — | New AI fault investigations opened |
| `reasoning_bridge_investigations_updated_total` | Counter | — | Existing investigations updated in place |
| `reasoning_bridge_recommendations_produced_total` | Counter | — | Actionable recommendations produced |
| `reasoning_bridge_recommendations_withheld_total` | Counter | — | Recommendations withheld (not corroborated / insufficient evidence) |
| `reasoning_bridge_class_change_updates_total` | Counter | — | `class_changed` transitions applied to an existing investigation |
| `reasoning_bridge_clear_transitions_processed_total` | Counter | — | `cleared` transitions processed |
| `reasoning_bridge_failures_total` | Counter | — | Unexpected failures while processing an alert-transition event |
| `reasoning_bridge_processing_latency_seconds` | Histogram | — | End-to-end per-event processing time |
| `reasoning_bridge_publish_failures_total` | Counter | — | Kafka publish failures for the reasoning-result event |
| `reasoning_bridge_worker_starts_total` | Counter | — | Worker process start count (compare against process start time to detect restarts) |

### Fault inference worker metrics (`backend/simulator/inference_worker/metrics.py`, v1.1)

The fault-inference worker consumes Kafka telemetry, assembles per-asset samples, and
runs the promoted model. It is a separate process from the API/worker and exposes its
own `/metrics` endpoint on port 9108 (scraped as job `odis-fault-inference-worker`).
See [Kafka Fault Inference Worker](../kafka-fault-inference-worker.md).

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `fault_inference_telemetry_events_consumed_total` | Counter | — | Telemetry events consumed |
| `fault_inference_samples_assembled_total` | Counter | — | Complete per-asset/timestamp samples assembled |
| `fault_inference_malformed_events_total` | Counter | `reason` | Input events rejected as malformed |
| `fault_inference_incomplete_sample_expirations_total` | Counter | — | Samples rejected as incomplete after timeout/eviction |
| `fault_inference_conflicting_duplicates_total` | Counter | — | Samples rejected due to a conflicting duplicate measurement |
| `fault_inference_late_samples_total` | Counter | — | Samples rejected as late |
| `fault_inference_results_total` | Counter | `status` (`warming_up`, `valid_prediction`, `insufficient_data`) | `fault_inference.v1` events published |
| `fault_inference_diagnoses_total` | Counter | `diagnosed_class` | `valid_prediction` results by diagnosed class |
| `fault_inference_alert_transitions_total` | Counter | `transition_type`, `diagnosed_class` | `fault_alert_transition.v1` events published |
| `fault_inference_active_asset_sessions` | Gauge | — | Asset sessions currently tracked by this worker process |
| `fault_inference_assembly_buffer_size` | Gauge | — | In-progress (asset, timestamp) samples buffered |
| `fault_inference_inference_latency_seconds` | Histogram | — | Promoted-model inference time per sample |
| `fault_inference_event_lag_seconds` | Histogram | — | Lag between a sample's `source_timestamp` and processing time |
| `fault_inference_publish_failures_total` | Counter | `topic_role` | Kafka publish failures, by target topic |
| `fault_inference_worker_starts_total` | Counter | — | Worker process start count |

### Outbox metrics (`outbox_metrics.py`, v1.1)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `outbox_pending_events` | Gauge | — | Undispatched `OutboxEvent` rows, sampled at the end of each dispatch cycle | `OutboxDispatcher.dispatch` |

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

### Forecast metrics (`forecast_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `forecast_inference_total` | Counter | — | Successful ONNX forecast inference requests | Telemetry forecast path (see [Telemetry Forecasting](telemetry-forecasting.md)) |
| `forecast_inference_failures_total` | Counter | — | Failed forecast inference requests | Telemetry forecast path |
| `forecast_inference_duration_seconds` | Histogram | — | ONNX inference latency | Telemetry forecast path |

### Health and readiness metrics (`health_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `worker_heartbeat_age_seconds` | Gauge | — | Age of the most recent worker heartbeat | Readiness check |
| `reasoning_jobs_pending` | Gauge | — | Reasoning jobs currently pending | Readiness check |
| `reasoning_jobs_failed_current` | Gauge | — | Reasoning jobs currently in FAILED status | Readiness check |
| `readiness_check_failures_total` | Counter | `dependency` | Readiness probe failures by dependency (database, engine, session_factory, reasoning_job_queue, worker) | `/health/ready` |

### MQTT bridge metrics (`mqtt_bridge_metrics.py`)

| Metric | Type | Labels | Purpose | Emitted from |
|--------|------|--------|---------|--------------|
| `mqtt_messages_received_total` | Counter | `topic`, `qos`, `retain` | Messages received from Mosquitto | `mqtt-bridge` |
| `mqtt_messages_forwarded_total` | Counter | `asset_id` | Messages successfully forwarded to `POST /observations` | `mqtt-bridge` |
| `mqtt_messages_ignored_total` | Counter | `reason` | Messages ignored (e.g. unparseable topic/payload) | `mqtt-bridge` |
| `mqtt_messages_acknowledged_total` | Counter | `outcome` | Messages explicitly acknowledged to the broker | `mqtt-bridge` |
| `mqtt_messages_unacknowledged_total` | Counter | `reason` | Deliveries left unacknowledged for broker redelivery | `mqtt-bridge` |

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

GET /monitoring/assets/{asset_id}/digital-twin  (cache miss)
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

# Fault-inference: is the model warming up or rejecting data?
sum by (status) (rate(fault_inference_results_total[5m]))

# Reasoning bridge: are recommendations being withheld?
sum(rate(reasoning_bridge_recommendations_withheld_total[5m]))

# Is the outbox backing up?
outbox_pending_events
```

## Grafana dashboard and alert rules (v1.1)

`infra/docker/grafana/dashboards/odis-monitoring.json` is provisioned automatically by
the `grafana` Compose service. It has one row per subsystem; the **AI Fault Alert
Pipeline** row covers the reasoning-bridge and fault-inference worker metrics above
(results by status, Kafka publish failures, corroboration results, recommendations
produced vs. withheld, reasoning-bridge failures, outbox backlog, worker restarts).

`infra/docker/prometheus/rules.yml` (mounted alongside `prometheus.yml`, referenced via
`rule_files`) defines a small set of demo/reference alerts — worker/API unavailability,
sustained Kafka publish failures, no valid inference despite telemetry flow, a high
insufficient-data rate, a high reasoning-bridge failure rate, and outbox backlog growth.
These thresholds are chosen to be obviously-broken indicators for a single-tenant demo
deployment; they are **not** calibrated SLOs.

**Known gap:** `k8s/config/prometheus-configmap.yaml` only scrapes the `api` service —
the fault-inference worker and reasoning-bridge worker have no Kubernetes Deployment
manifest yet (`k8s/worker/deployment.yaml` covers only the original digital-twin
reasoning worker), so there is nothing to scrape there. The Compose path
(`infra/docker/prometheus/prometheus.yml`) already scrapes both. Add the k8s scrape
jobs in the same change that adds their Deployments.

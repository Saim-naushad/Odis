# Kafka streaming fault-inference worker (PR177)

Consumes canonical Plant Alpha telemetry from Kafka, assembles bounded
per-asset inference state, runs the PR176-promoted fault model
incrementally, and publishes versioned diagnosis and alert-transition
events for a future deterministic-reasoning consumer (PR178).

Non-goals for this PR: deterministic-reasoning integration, recommendation
generation, FastAPI endpoints, database persistence, dashboard UI, model
retraining/calibration, MLflow/model registry, cross-process
inference-state persistence, automatic model reload, autonomous plant
control.

## Why this shape

Before writing any code, the existing architecture was audited (see
`backend/app/infrastructure/events/kafka_integration_event_publisher.py`
and `backend/app/infrastructure/mqtt/*`). Two findings shaped everything
below:

1. **No Kafka consumer existed anywhere in ODIS.** The only Kafka client
   usage was a synchronous `kafka-python` *producer*
   (`KafkaIntegrationEventPublisher`), publishing a curated set of
   integration events to one hardcoded topic. This worker reuses the same
   client library and lazy-import style — it is not a second Kafka
   abstraction, it is the first consumer built on the existing one.
2. **Canonical telemetry never touched Kafka.** It only ever flowed
   Simulator → HTTP `POST /observations`, or Simulator → MQTT → mqtt-bridge
   → HTTP. So this PR also adds the smallest possible producer-side piece:
   `backend.simulator.publishers.kafka_publisher.KafkaObservationPublisher`,
   a sibling to the existing `Http`/`MqttObservationPublisher`, reusing the
   same `observation_to_payload` mapping and per-measurement granularity
   the MQTT publisher already uses.

The worker itself lives at `backend/simulator/inference_worker/` —
sibling to PR176's `backend/simulator/inference/`, not inside
`backend/app/`. `backend/simulator/` has zero existing dependency on
`backend/app` (its publishers only ever talk to the platform over
HTTP/MQTT); this worker preserves that boundary rather than introducing a
new one, while matching `backend/app`'s conventions *by pattern*
(`structlog` JSON logs, `prometheus_client` counters, `pydantic-settings`,
`kafka-python`) in small local modules (`logging_setup.py`, `metrics.py`)
rather than importing `backend.app.*` directly.

## Data flow

```
PlantAlphaSimulator (--transport kafka)
  → odis.telemetry.observations.v1 (Kafka, one message per measurement)
  → inference_worker: validate → assemble → FaultInferenceManager.ingest
  → odis.fault.inference-results.v1   (every processed sample)
  → odis.fault.alert-transitions.v1   (only on a state-machine transition)
  → odis.fault.telemetry-data-quality.v1  (malformed/incomplete/conflicting/late)
```

The existing Simulator → MQTT → mqtt-bridge → HTTP path (used by the
dashboard) is untouched; `--transport kafka` is an additional, opt-in
publisher for feeding this worker.

## Live simulator synchronization

**Root cause.** The live simulator's existing publish loop
(`backend/simulator/__main__.py`) runs two independent cadences: `core_due`
publishes `stack_temperature`/`stack_pressure`/`current`/`voltage`/
`fuel_flow` (from `core_observations_from_machine`), `derived_due`
publishes `power_output`/`coolant_flow`/`efficiency` (from
`derived_observations_from_state`), each on its own configurable interval
(`core_publish_interval_seconds` default 15s, `derived_publish_interval_
seconds` default 60s). Each branch calls `datetime.now(UTC)`
**separately**, so even when both happen to fire in the same loop pass
their timestamps differ by however many microseconds elapsed between the
two calls. `TelemetrySample.from_observations` requires every observation
in a sample to share one *exact* timestamp — so a complete sample never
assembles from this loop's natural output, regardless of cadence
configuration. This is a real, pre-existing characteristic (present since
before this PR), not a defect introduced by the Kafka work; HTTP/MQTT/the
dashboard tolerate it because neither consumes "one complete synchronized
sample" — they read/display each measurement independently, keyed by its
own timestamp, and no existing consumer joins core+derived rows by exact
timestamp equality.

Machine state itself is only ever advanced inside the `core_due` branch
(`scenario.tick(fleet, settings.sim_dt_seconds)`); `derived_due` reads
whatever `machine.state` currently holds without ticking. So "the same
machine state" already exists at any instant — the fix only needs one
shared timestamp and one shared read of that state, not new physics.

**Chosen design: A — shared snapshot timestamp**, the smallest
architecture-compatible fix. A new `_publish_kafka_snapshot` function
(`backend/simulator/__main__.py`) ticks the fleet once, captures one
`datetime.now(UTC)`, and builds *both* core and derived observations from
that one machine state and that one timestamp, reusing
`core_observations_from_machine`/`derived_observations_from_state`
unchanged — no physics formulas are duplicated. `_run_kafka_loop` repeats
this at `kafka_sample_interval_seconds`; the existing dual-cadence loop
(extracted, unchanged, into `_run_dual_cadence_loop`) still drives HTTP
and MQTT exactly as before. The two loops are mutually exclusive (`main()`
branches once on `settings.transport`), so this is a pure addition, not a
behavior change, for HTTP/MQTT.

Design B (a Kafka-specific canonical builder layered on top of the
existing separate cadences) and C (a single complete-sample Kafka event,
changing the worker's per-measurement input contract) were both rejected:
B would still need one shared timestamp/state capture per Kafka publish,
making it strictly more code than A for the same result; C would abandon
the per-measurement granularity that already matches the MQTT publisher's
convention, for no benefit once A resolves the actual timestamp problem.

The assembler's exact-timestamp-equality requirement is unchanged —
`SampleAssembler` still does not do rounding, tolerance windows, or
nearest-neighbor matching; the fix is entirely on the producer side.

## Cadence contract

The promoted model's window/rate/residual features were trained assuming
samples arrive `DT_SECONDS` (`10.0`) of *simulated* time apart —
`FaultInferenceSession.ingest` derives its internal `elapsed_sim_seconds`
clock from sample **count** (`(n+1) * DT_SECONDS`), never from a sample's
wall-clock timestamp gap (see that module's docstring). So the quantity
that must actually be correct is how much simulated time
`scenario.tick(...)` advances per published sample — not the wall-clock
spacing between publishes (which only needs to be strictly increasing,
for `NonMonotonicTimestampError`).

Two independent settings, both on `SimulatorSettings`:
- **`kafka_sample_interval_seconds`** (default `10.0`, the trained
  cadence) — the `dt_seconds` passed to `scenario.tick()`. This is the
  value that matters for feature correctness; `_run_kafka_loop` logs a
  `WARNING` at startup if an operator overrides it away from the trained
  value, since doing so silently produces features the model was never
  trained to see.
- **`kafka_publish_interval_seconds`** (default `10.0`, matching the
  above — a realistic, real-time-paced stream) — the *wall-clock* seconds
  slept between publishes. Feature correctness does not depend on real
  elapsed time at all, only on the simulated `dt_seconds` per tick, so
  this can be lowered independently to accelerate scripted demos/smoke
  tests without affecting model correctness — it only changes how
  quickly a fixed number of correctly-spaced samples are produced in
  real time. (This distinction was a real gap surfaced by this PR's own
  first smoke test attempt: coupling the two meant a scripted scenario
  whose fault phases are expressed in cumulative simulated seconds took
  hours of real time to complete; see "Actual simulator end-to-end
  smoke" below.)

Both are deliberately independent of `sim_dt_seconds` (HTTP/MQTT's own
physics-tick step, default 45s — demo-paced, not model-trained) and of
`core_publish_interval_seconds`/`derived_publish_interval_seconds` (also
HTTP/MQTT-only). None of the three are read by the Kafka loop.

`kafka_sample_interval_seconds`'s default is duplicated in
`backend/simulator/config.py` as `_TRAINED_INFERENCE_CADENCE_SECONDS`
rather than imported from `backend.simulator.dataset.features.config.
DT_SECONDS` — that module's package (`backend.simulator.dataset.
features`) unconditionally imports its pyarrow-dependent `generate`
submodule at package-init time, and the live simulator/demo-plant image
otherwise has no dependency on `pyarrow` at all (confirmed the hard way:
the first corrected build crashed on `ModuleNotFoundError: No module
named 'pyarrow'`). A dedicated test keeps the two values in sync.

## Single-source telemetry provenance (`kafka+http` transport)

PR178's reasoning bridge (`docs/reasoning-bridge.md`) corroborates a
confirmed ML alert against observations persisted through the platform's
normal HTTP ingestion path. Running two independent simulator
processes — one `--transport kafka` feeding this worker, a separate
`--transport http` feeding persistence — only produces telemetry that
*resembles* the Kafka stream; different processes mean different
`run_id`s, different tick cadences, and no shared `Observation` objects,
so the "corroborating" data is never provably the same telemetry that
produced the alert. That gap is closed by a third transport,
`--transport kafka+http` (`SimulatorSettings.transport = "kafka+http"`),
which routes through the *same* `_run_kafka_loop`/`_publish_kafka_snapshot`
single-tick, single-timestamp path this worker already depends on, but
publishes through
`backend.simulator.publishers.composite_publisher.CompositeObservationPublisher`
— a small fan-out wrapper that sends the one already-constructed list of
`Observation` objects per tick to both a `KafkaObservationPublisher` and
an `HttpObservationPublisher`, in that fixed order, unchanged. No
telemetry is recomputed per transport and the fleet is never ticked
twice for one published sample.

Delivery is not a distributed transaction: if the Kafka publish succeeds
and the subsequent HTTP publish fails (or vice versa), the earlier
publish is not rolled back, and the exception propagates uncaught rather
than being retried by re-ticking the fleet — retrying with the same
already-constructed observations would be safe (`observation_id()` is
fully deterministic, so a duplicate HTTP retry is rejected with `409`
rather than double-persisted), but this composite does not implement
retry logic itself; that is left to process supervision (e.g. a
container restart), consistent with the rest of this worker's existing
crash-on-publish-failure convention. See `docs/reasoning-bridge.md`'s
"Publication and failure semantics" section for the corroboration side
of this contract, and `tests/backend/simulator/test_composite_publisher.py`
/ `tests/backend/simulator/test_kafka_http_fanout.py` for the tests that
pin identical ids/timestamps/values reaching both sinks from one tick.

## Topics and consumer group

| Role | Env var | Default |
| --- | --- | --- |
| Bootstrap servers | `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` |
| Input (telemetry) | `FAULT_INFERENCE_INPUT_TOPIC` | `odis.telemetry.observations.v1` |
| Results | `FAULT_INFERENCE_RESULTS_TOPIC` | `odis.fault.inference-results.v1` |
| Alert transitions | `FAULT_INFERENCE_ALERT_TRANSITIONS_TOPIC` | `odis.fault.alert-transitions.v1` |
| Data quality | `FAULT_INFERENCE_DATA_QUALITY_TOPIC` | `odis.fault.telemetry-data-quality.v1` |
| Consumer group | `FAULT_INFERENCE_CONSUMER_GROUP_ID` | `odis-fault-inference-worker` |

All defaults and remaining tunables (`FAULT_INFERENCE_BUNDLE_DIR`,
`FAULT_INFERENCE_ASSEMBLY_TIMEOUT_SECONDS`,
`FAULT_INFERENCE_MAX_BUFFERED_TIMESTAMPS_PER_ASSET`,
`FAULT_INFERENCE_MAX_TRACKED_ASSETS`, `FAULT_INFERENCE_POLL_TIMEOUT_MS`,
`FAULT_INFERENCE_PUBLISH_MAX_RETRIES`,
`FAULT_INFERENCE_PUBLISH_RETRY_BACKOFF_SECONDS`,
`FAULT_INFERENCE_METRICS_PORT`) are defined and validated in
`backend/simulator/inference_worker/config.py`.

There is no separate dead-letter topic — the existing codebase has no DLQ
convention to reuse, and one differentiated data-quality topic (`reason`
field: `malformed` | `incomplete_timeout` | `conflicting_duplicate` |
`late`) is the smallest addition that satisfies spec section 10 without
inventing a new multi-topic DLQ convention. `insufficient_data` is never
published here — it is a valid inference-runtime outcome carried on
`fault_inference.v1` instead (see `events.py`'s module docstring).

## Input event contract — `telemetry.observation.v1`

One canonical measurement reading per message, matching the MQTT
publisher's existing per-measurement granularity:

```json
{
  "event_id": "...",
  "event_version": "v1",
  "asset_id": "fuel-cell-stack-01",
  "timestamp": "2026-07-21T00:00:00+00:00",
  "measurement_name": "stack_temperature",
  "value": 65.2,
  "unit": "celsius",
  "source": "plant-alpha-simulator"
}
```

Validated by `events.validate_telemetry_event`, which never raises
anything except a `TelemetryEventValidationError` subclass: unsupported
`event_version`, missing field, unparseable timestamp, unknown
`measurement_name`, unit mismatch (reusing
`backend.simulator.inference.telemetry.CANONICAL_UNITS`, never
redeclared), non-finite value. Malformed input is routed to the
data-quality topic and never crashes the worker.

## Sample assembly (`assembly.py`)

Telemetry arrives one measurement per message, so `SampleAssembler`
assembles exactly one complete `TelemetrySample` per `(asset_id,
timestamp)` before anything reaches `FaultInferenceManager`:

- **identical duplicate** (same value/unit for an already-buffered
  measurement): idempotently ignored;
- **conflicting duplicate** (different value/unit): rejects the whole
  in-progress sample (`conflicting_duplicate`);
- **incomplete after `assembly_timeout_seconds`**: rejected
  (`incomplete_timeout`), swept once per poll cycle;
- **late** (timestamp not strictly after the asset's last *completed*
  timestamp): rejected (`late`) — this worker never backfills an
  already-processed inference timestamp, matching
  `FaultInferenceSession.ingest`'s own strict-monotonic requirement.

Bounded state: at most `max_buffered_timestamps_per_asset` in-progress
timestamps per asset (oldest evicted first, reported as
`incomplete_timeout`) and at most `max_tracked_assets` asset buffers
tracked at once (least-recently-active evicted first). Measurement
ordering within an assembled sample is always the fixed tuple
`REQUIRED_MEASUREMENTS + ("efficiency",)`, regardless of arrival order.

## Delivery and idempotency semantics

**At-least-once consumption, idempotent downstream identity.** The
consumer uses manual offset commit (`enable_auto_commit=False`); the
worker commits only after a message's full outcome — buffered, published,
or rejected-and-reported — has succeeded (`worker.py`'s `poll_once`). A
publish failure (after `publish_max_retries` retries) stops the current
poll batch without committing, so the triggering message (and anything
after it in that batch) is redelivered on the next poll.

Every published `fault_inference.v1` and `fault_alert_transition.v1` event
has a **deterministic `event_id`** — `identity.deterministic_event_id`,
`uuid5` over a fixed private namespace seeded from
`(event_type, asset_id, source_timestamp, ...)`. This is a **deliberate,
documented departure** from the rest of this codebase's convention: every
existing ID-minting site (`backend/app/application/*`) uses random
`uuid4()`. That convention is fine for events whose only consumer treats
duplicates as harmless; it is not sufficient here, since replayed input
must not mint a second, distinct diagnosis/alert event downstream. The
same logical output — same asset, same source timestamp, same model
version, same result type — always gets the same `event_id`, so a future
consumer (PR178) can deduplicate on `event_id` alone.

Consequences, spelled out:
- **duplicate input events** (identical measurement re-delivered): the
  assembler ignores them idempotently; no re-ingestion into the model.
- **worker restart**: a fresh process has no record of what a prior
  process already committed offsets for; Kafka redelivers from the last
  committed offset. See "State and restart behavior" below.
- **offset replay** (consumer group reset, rebalance redelivery): already-
  processed samples are rejected by the assembler's `late` check (their
  timestamp is not after `latest_processed_timestamp`) rather than
  re-ingested — see `test_idempotency.py::
  test_replayed_full_sample_after_completion_is_rejected_as_late`.
- **duplicate published events**: even if the same result were
  regenerated (e.g. after a crash mid-batch, before commit), the
  deterministic `event_id` is identical, so a consumer deduplicating on
  `event_id` sees no effective duplicate.

One documented gap: the periodic timeout sweep (`worker._sweep_timeouts`)
is time-driven, not tied to a specific consumer offset. If publishing its
resulting data-quality event fails after retries, that event is dropped —
the underlying telemetry messages' offsets were already committed when
each measurement was ingested, so this is a monitoring gap, not a
telemetry-loss gap.

## State and restart behavior

Per-asset feature history and alert state live only in the worker
process's memory (`FaultInferenceManager`/`FaultInferenceSession`, both
unchanged from PR176 — see `docs/runtime-inference.md`'s own "Restart /
state limitations"). A restart:
- always begins cold — every asset re-enters warm-up
  (`InferenceStatus.WARMING_UP`) until `LONGEST_WINDOW_SAMPLES` new
  samples arrive;
- never corrupts Kafka processing — the new process starts from the
  consumer group's last committed offset like any other consumer restart;
- is visible via metrics/logs: `fault_inference_worker_starts_total`
  increments once per process start (compare against process start time
  in Prometheus to spot restarts), and `fault_inference_worker_started`/
  `fault_inference_worker_bundle_verified` are logged with the verified
  model/policy versions on every start.

No Redis/database state persistence is added in this PR — the existing
worker architecture doesn't make it free, and PR176 explicitly left that
decision to "a future Kafka integration." Restart-induced warm-up is a
real, visible limitation, not hidden behind a fallback.

## Output event contracts

`fault_inference.v1` — published for **every** processed sample,
regardless of status:

```json
{
  "event_id": "...", "event_version": "v1",
  "occurred_at": "...", "asset_id": "...", "source_timestamp": "...",
  "status": "valid_prediction",
  "diagnosed_class": "cooling_degradation",
  "class_scores": {"healthy": 0.02, "cooling_degradation": 0.91, "...": "..."},
  "maximum_score": 0.91,
  "evidence": [{"label": "...", "value": 0.91, "detail": "..."}],
  "alert_state": "confirmed_cooling_degradation",
  "model_system_version": "...", "model_hash": "...", "policy_hash": "...",
  "feature_schema_version": "...",
  "reason_codes": []
}
```

`fault_alert_transition.v1` — published only when
`InferenceResult.alert_event` is present (never once per confirmed row):

```json
{
  "event_id": "...", "event_version": "v1",
  "occurred_at": "...", "asset_id": "...", "source_timestamp": "...",
  "transition_type": "confirmed",
  "from_state": "healthy", "to_state": "confirmed_cooling_degradation",
  "diagnosed_class": "cooling_degradation",
  "evidence": [...], "model_system_version": "...", "model_hash": "...",
  "policy_hash": "...", "feature_schema_version": "...",
  "class_scores": {"healthy": 0.02, "cooling_degradation": 0.91, "...": "..."},
  "maximum_score": 0.91
}
```

`transition_type` maps PR176's `AlertEvent.event_type` (`new_alert` /
`class_change` / `cleared`) to `confirmed` / `class_changed` / `cleared`
per this PR's spec vocabulary. `feature_schema_version`/`class_scores`/
`maximum_score` were added by PR178 — the reasoning-bridge consumer's own
AI-evidence contract requires the model's native scores and schema
version, not just the curated `evidence` summary; this is a small,
backward-compatible extension, not a rewrite (every other field/consumer
of this event is unaffected).

`telemetry.data-quality.v1` — one differentiated `reason` (`malformed` |
`incomplete_timeout` | `conflicting_duplicate` | `late`) per rejected
input; `insufficient_data` is never reported here (see above).

## Bounded state and throughput assumptions

Single consumer, single thread, strictly sequential processing — the
input topic is keyed by `asset_id`, so one asset's messages stay ordered
on one partition and are handled in order. This matches Plant Alpha's
actual load (4 assets, ~15s telemetry cadence) comfortably; horizontal
scaling across partitions (per-partition session affinity) is future
work, not attempted here. Per-asset history, the assembly buffer, and
tracked-asset count are all bounded (see "Sample assembly" above); no
per-asset consumer, no unbounded task creation.

## Metrics

Prometheus counters/gauges/histograms in
`backend/simulator/inference_worker/metrics.py`, exposed via
`prometheus_client.start_http_server(FAULT_INFERENCE_METRICS_PORT)`
(default `9108`) — a dedicated metrics server, since this worker is a
separate process from `api` and nothing scrapes `backend.app.worker_main`
today either. No raw `asset_id` label anywhere; `class`/`status`/`reason`
labels stay on bounded, low-cardinality vocabularies.

Key metrics: `fault_inference_telemetry_events_consumed_total`,
`fault_inference_samples_assembled_total`,
`fault_inference_malformed_events_total{reason}`,
`fault_inference_incomplete_sample_expirations_total`,
`fault_inference_conflicting_duplicates_total`,
`fault_inference_late_samples_total`,
`fault_inference_results_total{status}`,
`fault_inference_diagnoses_total{diagnosed_class}`,
`fault_inference_alert_transitions_total{transition_type,diagnosed_class}`,
`fault_inference_active_asset_sessions`,
`fault_inference_assembly_buffer_size`,
`fault_inference_inference_latency_seconds`,
`fault_inference_event_lag_seconds`,
`fault_inference_publish_failures_total{topic_role}`,
`fault_inference_worker_starts_total`.

## Local Compose startup

```bash
docker compose --profile demo up --build -d kafka fault-inference-worker
```

The worker depends on `kafka` (`service_healthy`); its `Dockerfile`
(`infra/docker/fault-inference-worker/Dockerfile`) installs the `ml`
extra (scikit-learn/joblib/numpy — needed to load and run the promoted
pipeline) and bundles the committed `artifacts/models/plant_alpha_fault_v1/`
directory. Prometheus is pre-configured to scrape
`fault-inference-worker:9108` (`infra/docker/prometheus/prometheus.yml`).

## Smoke test

Containerized, fully isolated network (`odis-internal`), using the real
Plant Alpha simulator end to end — no helper/hand-built producer:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d kafka

docker build -f infra/docker/fault-inference-worker/Dockerfile -t odis-fault-inference-worker:local .
docker build -f infra/docker/demo-plant/Dockerfile -t odis-demo-plant:local .

docker run -d --name fiw-smoke --network odis_odis-internal \
  -e KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
  odis-fault-inference-worker:local

docker run -d --name plant-smoke --network odis_odis-internal \
  -e SIMULATOR_TRANSPORT=kafka \
  -e SIMULATOR_KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
  -e SIMULATOR_KAFKA_PUBLISH_INTERVAL_SECONDS=0.3 \
  -e SIMULATOR_SCENARIO_SCRIPT=demo_presentation \
  -e SIMULATOR_ASSET_IDS=fuel-cell-stack-01 \
  odis-demo-plant:local
```

`SIMULATOR_KAFKA_PUBLISH_INTERVAL_SECONDS=0.3` only accelerates wall-clock
pacing for the demo; `kafka_sample_interval_seconds` stays at its default
`10.0` (the trained cadence) throughout — the "Cadence contract" section
above.

**Actual results from this exact run** (single asset, `demo_presentation`
script, real physics, real promoted model — no hand-built fixture):

- `fault_inference_worker_bundle_verified`: `model_system_version=
  plant_alpha_fault_v1`, `model_hash=30ae2bad5eca428b78e72756c49e71f8
  9c0db8584b79ce3fef7790d7d6067a8f`, `feature_schema_version=1.0`.
- First telemetry/warm-up result: `source_timestamp=2026-07-21T16:26:
  27.727800+00:00`, `status=warming_up`.
- 11 consecutive `warming_up` results, then the 12th sample's result:
  `status=valid_prediction`, `diagnosed_class=healthy` — confirming
  `LONGEST_WINDOW_SAMPLES`-sample warm-up exactly, with the real
  simulator's own telemetry (not a synchronized helper fixture).
- As the scripted `cooling_degradation` phase progressed, diagnosed
  class shifted `healthy → hydrogen_supply_issue → cooling_degradation`
  before settling; **one** `fault_inference_alert_transition` fired at
  `source_timestamp=2026-07-21T16:26:43.124453+00:00`
  (`transition_type=confirmed`, `from_state=healthy`,
  `to_state=confirmed_cooling_degradation`), despite 98 subsequent
  `valid_prediction` rows diagnosing `cooling_degradation` — proving no
  duplicate transition events for repeated confirmed rows. A second,
  independent transition later fired at `2026-07-21T16:27:10.327554+00:00`
  (`transition_type=class_changed`, `to_state=confirmed_hydrogen_supply_
  issue`) as the script's phase changed again — also exactly one event,
  not one per row.
- **Zero** `incomplete_timeout`/`conflicting_duplicate`/`late` events for
  the entire run — `odis.fault.telemetry-data-quality.v1` was never even
  created as a topic, confirming the dual-cadence bug this correction
  fixes no longer reproduces with the real simulator.
- Metrics at run end: `fault_inference_telemetry_events_consumed_total=
  1248` (156 samples × 8 measurements/sample), `fault_inference_samples_
  assembled_total=156`, `fault_inference_incomplete_sample_expirations_
  total=0`, `fault_inference_results_total{status="warming_up"}=11`,
  `fault_inference_results_total{status="valid_prediction"}=145`,
  `fault_inference_alert_transitions_total{...}=1` for each of the two
  transition/class combinations above, `fault_inference_event_lag_
  seconds_sum=4.93` over 156 samples (~32ms average — near-zero, as
  expected for a locally networked container-to-container stream).
- End-to-end lag (telemetry publish → worker log line): consistently
  under 300ms per sample, confirmed directly in `docker logs fiw-smoke`
  timestamps against `docker logs plant-smoke`.
- Verified directly on the real topics via `kafka-console-consumer.sh`
  (not just worker logs) — both `odis.fault.inference-results.v1` and
  `odis.fault.alert-transitions.v1` contain the exact events described
  above, with `model_hash`/`policy_hash`/`feature_schema_version`
  present on every record.

Injecting a deliberate `insufficient_data` event (e.g. a physically
implausible `fuel_flow` value on the Kafka transport) produces a
`status=insufficient_data` result instead of a crash — exercised
separately in `tests/backend/simulator/inference_worker/test_worker.py::
test_insufficient_data_result_is_emitted` against the real worker code
path (not re-run live here, since it requires deliberately malformed
physics values rather than the scripted scenario's normal behavior).

## What PR178 will consume next

`fault_inference.v1` and `fault_alert_transition.v1`, both already
carrying `model_system_version`/`model_hash`/`policy_hash`/
`feature_schema_version` for provenance and a deterministic `event_id`
for dedup — a future deterministic-reasoning consumer (PR178) can key off
either topic without needing to re-derive anything this worker already
computed. This PR does not integrate with `src/application`'s reasoning
pipeline, generate recommendations, or persist anything to a database.

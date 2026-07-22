# Reasoning bridge: confirmed AI alerts → deterministic ODIS reasoning (PR178)

Bridges PR177's confirmed ML fault-alert events into ODIS's existing
investigation/timeline infrastructure: a confirmed alert is treated as one
piece of evidence, deterministically corroborated against observable
telemetry, and — only when corroboration supports it — turned into a
bounded, traceable operator recommendation.

Non-goals: dashboard UI, new model work, retraining, calibration,
autonomous control, actuator commands, MLflow, model registry, new fault
classes, recovery modeling, long-term cross-process inference-state
persistence.

## Authority boundary

```
ML (PR176/177):  detects and classifies a suspected fault
                  ↓ (evidence only)
Deterministic reasoning (this PR): validates evidence
                                   determines the fault occurrence
                                   applies rules
                                   creates a recommendation
                                   records provenance
```

The model never constructs an `Action`, `DecisionPlan`, or final
recommendation directly. Concretely, in code:

- `backend.app.application.reasoning_bridge.corroboration` never reads
  `class_scores`/`maximum_score` at all — its functions accept only
  `Observation` sequences (enforced structurally by their signatures, and
  by `test_corroboration.py::test_corroboration_never_reads_model_scores`).
- `backend.app.application.reasoning_bridge.recommendation_policy.
  build_recommendation` takes a `CorroborationOutcome` (a deterministic
  verdict) — again no score/probability parameter — and is the *only*
  place a `FaultRecommendation` is constructed.
- The alert-policy's own confirmation (PR175's persistence-based FSM,
  already "the deterministic gate" before a transition event is ever
  published) is reused as-is; this PR adds no second, arbitrary
  model-score threshold on top of it (spec section 9).

## Reasoning bridge architecture

**Why this doesn't call `ReasoningSession`.** The audit for this PR
established that `src.application.reasoning_session.ReasoningSession.run`
is hard-wired to `Sequence[Observation]` with no extension point for
injecting a non-observation evidence item — every stage builds its
`ReasoningContext` directly from an observation sequence, and
`observation_service.py`'s own gate (`_can_run_reasoning`) requires
`len(observations) >= 2` before reasoning runs at all. Forcing an ML
alert through that pipeline would mean fabricating fake `Observation`
rows to represent it (semantically wrong) or invasively changing
`src/domain`/`src/application` (the transport-agnostic reasoning core
CLAUDE.md protects). Instead, this bridge is a small, separate
deterministic flow that reuses only the *infrastructure* those stages
also depend on: `UnitOfWork`, the timeline repository, and the same
"one service call → one UoW → one commit" convention
`InvestigationService.record_transition` already uses.

**Where it lives.** `backend/app/application/reasoning_bridge/` (pure
application logic, no Kafka) + `backend/app/infrastructure/
reasoning_bridge/` (Kafka I/O) + entry point
`backend/app/reasoning_bridge_worker_main.py` — inside `backend/app/`,
not `backend/simulator/`, because this worker needs full read/write
access to `backend.app.domain`/`backend.app.application` (the
investigation/timeline/UoW machinery), which `backend/simulator/
inference_worker/` deliberately has zero dependency on. `backend/app` and
`backend/simulator` still have no dependency on each other in either
direction — `kafka_io.py` here is a small, local reimplementation of the
same thin consumer/producer wrapper shape PR177 already established, not
an import from it.

**"AI fault investigation" is a new, separate concept from
`InvestigationEvent`.** `backend.app.domain.investigation.
InvestigationEvent` tracks an *operator's* response (acknowledge /
investigate / resolve) to an existing `Recommendation` — it has no
fault-class dimension at all (confirmed by its migration's schema: `id,
asset_id, recommendation_id, status, actor_id, actor_display_name,
occurred_at, notes` — nothing else). This PR's "AI fault investigation"
is a system-detected occurrence (asset + diagnosed class), a different
concept entirely, so it gets its own small domain type
(`backend.app.domain.ai_fault_evidence.AiFaultEvidence`) rather than
overloading the operator-transition model.

## Class mappings and corroboration rules

`backend.app.application.reasoning_bridge.fault_class_mapping.
FAULT_CLASS_MAPPINGS` — exactly the three classes the promoted
`plant_alpha_fault_v1` model supports; `healthy` and anything else
(no invented classes) are rejected before reaching this map.

| Fault class | Situation type | Relevant measurements | Allowed categories |
| --- | --- | --- | --- |
| `cooling_degradation` | `cooling_system_degradation` | stack_temperature, coolant_flow, current | investigate, monitor |
| `hydrogen_supply_issue` | `hydrogen_supply_degradation` | fuel_flow, voltage, current, power_output | investigate, monitor |
| `sensor_anomaly` | `sensor_reading_anomaly` | stack_temperature, current, voltage, fuel_flow | investigate, monitor |

`mitigate` is never an allowed category for any class in this PR — no
deterministic load-reduction/isolation threshold exists yet to justify
one (see "Recommendation safety" below).

**Corroboration** (`corroboration.py`) reuses
`src.application.trend_detector.TrendDetector` — the codebase's own
existing, calibrated trend primitive — over recent observations fetched
from the existing `ObservationRepository`. Rules, deterministic and
documented by a stable `<fault_class>.<condition>` rule id:

- **cooling_degradation**: `stack_temperature` INCREASING + `coolant_flow`
  DECREASING → `corroborated`; INCREASING + STABLE →
  `partially_corroborated`; INCREASING + also INCREASING (compensating)
  → `not_corroborated`; not INCREASING → `not_corroborated`; too little
  history → `insufficient_evidence`.
- **hydrogen_supply_issue**: `fuel_flow` DECREASING + `voltage` DECREASING
  → `corroborated`; DECREASING + STABLE → `partially_corroborated`;
  `fuel_flow` not DECREASING → `not_corroborated` (a load-change
  explanation, spec section 7); too little history →
  `insufficient_evidence`.
- **sensor_anomaly**: `stack_temperature` shifts while `current`/
  `voltage`/`fuel_flow` all stay STABLE → `corroborated` (physically
  inconsistent with a real thermal event); some but not all of them also
  shift → `partially_corroborated`; all of them shift too →
  `not_corroborated` (looks like a real physical event, contradicting the
  sensor-anomaly hypothesis); `stack_temperature` itself is STABLE →
  `not_corroborated`; too little history → `insufficient_evidence`.

## Investigation and recommendation lifecycle

`investigation_lifecycle.decide_investigation` — asset-scoped, not
(asset, class)-scoped: at most one AI fault investigation is open per
asset. `investigation_id` is minted once (first confirmed alert), reused
across `class_changed` transitions (recording
`previous_diagnosed_fault_class`), and retained (never deleted) when
`cleared` (`investigation_status` flips to `CLEARED`). A new confirmed
alert after a clear always mints a *new* `investigation_id` — it never
reopens the cleared occurrence.

`cleared` transitions never run corroboration or produce a
recommendation (`corroboration_result="not_applicable"`,
`recommendation=None`) — clearing doesn't diagnose anything.

Recommendation status by corroboration result (spec sections 8, 12):

| Corroboration result | Recommendation | Urgency | Category |
| --- | --- | --- | --- |
| `corroborated` | produced (fault-specific steps) | `ELEVATED` | investigate |
| `partially_corroborated` | produced (verification steps only) | `INSPECTION_REQUIRED` | investigate |
| `not_corroborated` | withheld (disagreement recorded, not discarded) | `INFORMATIONAL` | monitor |
| `insufficient_evidence` | withheld (request more telemetry) | `INFORMATIONAL` | monitor |

**Recommendation safety.** `URGENT` is never produced by this PR — no
deterministic persistence/impact threshold exists yet to justify
escalating past `ELEVATED` (spec section 12: "avoid claiming emergency
severity without a deterministic threshold"); a future PR can add
duration/impact-based escalation once such a threshold is defined.
`sensor_anomaly`'s recommended/verification steps never suggest plant
intervention (no "shut down"/"reduce load"/"isolate"/"trip" language) —
only comparison against a redundant/manual reading and wiring/calibration
inspection.

## Score-language caveat

`class_scores`/`maximum_score` are the promoted model's native,
**uncalibrated** diagnostic/ranking scores — never "confidence" or "X%
probability the fault is real" anywhere they are logged, persisted, or
published. `AiFaultEvidence` stores them purely as evidence metadata;
`corroboration.py`/`recommendation_policy.py` never read them at all —
corroboration and urgency come only from deterministic telemetry rules
and the alert policy's own already-confirmed diagnosis (spec section 9:
prefer that fact "rather than adding another arbitrary model-score
threshold").

## Corroboration evidence provenance (blocking correction)

The first end-to-end smoke test for this PR ran two independent
simulator processes — one `--transport kafka` feeding the ML alert path,
a separate `--transport http` seeding the database for corroboration.
That is a real provenance gap: two processes mean two different
`run_id`s and independent tick cadences, so the "corroborating"
observations only resembled the telemetry that produced the alert, they
were never provably the same readings. `ReasoningBridgeService` has no
way to distinguish that from reasoning against unrelated historical
data, and neither does an operator reading the resulting recommendation.

**Fix: single-source publication, not a service-layer patch.** The
reasoning bridge's own corroboration query was already correct (see
below); the gap was entirely upstream, in how the demo/smoke topology
produced telemetry. `backend.simulator.publishers.composite_publisher.
CompositeObservationPublisher` fans out one simulator tick's
already-constructed `Observation` objects — the same instances — to both
`KafkaObservationPublisher` and `HttpObservationPublisher`, wired in via
a new `--transport kafka+http`
(`docs/kafka-fault-inference-worker.md`'s "Single-source telemetry
provenance" section has the full design and failure-semantics writeup).
Running the platform this way means the observations
`ReasoningBridgeService._corroborate` later loads from Postgres are
byte-identical (same id, timestamp, value, unit) to what
fault-inference-worker consumed from Kafka to produce the alert — not a
second, independently-ticked approximation of it.

**Corroboration window is already asset- and time-scoped at the query
level**, not just by convention: `_corroborate` computes
`start = event.source_timestamp - corroboration_window_seconds` (default
900s) and `end = event.source_timestamp`, then calls
`SqlAlchemyObservationRepository.list_by_asset_in_time_range(event.
asset_id, start=start, end=end, measurement_type=..., ...)`, whose SQL
filters on `asset_id == event.asset_id AND timestamp >= start AND
timestamp <= end`. Consequences, now pinned by dedicated tests in
`tests/backend/reasoning_bridge/test_reasoning_bridge_service.py`:

- **other-asset exclusion** — a corroborating series recorded under a
  different `asset_id` is never fetched, regardless of how well it would
  otherwise corroborate
  (`test_corroboration_only_uses_observations_from_the_alerts_own_asset`).
- **future exclusion** — observations timestamped after the alert's own
  `source_timestamp` are excluded by `timestamp <= end`
  (`test_corroboration_excludes_observations_after_the_alert_source_timestamp`).
- **staleness** — observations older than the window are excluded by
  `timestamp >= start`, falling back to `insufficient_evidence` rather
  than reasoning against out-of-window history
  (`test_corroboration_excludes_observations_older_than_the_window`).
- **traceable supporting ids** — `CorroborationOutcome.supporting_
  observation_ids` (surfaced on `AiFaultEvidence.recommendation.
  supporting_observation_ids`) names exactly the fetched, in-window,
  same-asset observations, never a stale or future one that happens to
  share the asset/measurement
  (`test_supporting_observation_ids_are_traceable_to_the_fetched_window`).
- **class-changed alignment** — each call to `process_alert_transition`
  uses *that event's own* `source_timestamp` for the window end, so a
  later `class_changed` transition corroborates against its own recent
  window, never a stale window carried over from the first alert in the
  investigation
  (`test_class_changed_corroboration_uses_the_new_events_own_source_timestamp`).

No new validation code was added to `_corroborate` itself — the SQL
`WHERE` clause is the enforcement point, and duplicating that logic as a
second, redundant in-Python check on the query's own output would only
be circular. What was missing, and is now added, is proof: tests that
pin this behavior explicitly instead of leaving it implicit in the
repository query.

## Idempotency

`AiFaultEvidence.id` is the source alert-transition event's own
deterministic `event_id` (PR177's `identity.deterministic_event_id`).
Persisting it is *simultaneously* "recording the evidence" and "the
idempotency check": `AiFaultEvidenceRepository.save` rejects a duplicate
id exactly like `SqlAlchemyObservationRepository.save()` already rejects
a duplicate observation id (existing repository check + `IntegrityError`
fallback). Replaying the same event returns the already-persisted row
(`ProcessingOutcome.is_duplicate=True`) and creates nothing new — no
duplicate investigation, corroboration result, timeline entry, or
outbound event (the outbound `fault_reasoning_result.v1` event's own
`event_id` is also deterministic, seeded from `(source_event_id,
investigation_id)`, so even a duplicate publish attempt produces the
same event_id downstream consumers can deduplicate on).

## Persistence

One new table, `ai_fault_evidence` (migration
`h4i5j6k7l8m9_add_ai_fault_evidence_table.py`), covering evidence +
corroboration + recommendation (as a JSON column, matching this
codebase's existing `OutboxEvent.payload` JSON-column convention) +
investigation linkage — deliberately one small table rather than several,
per spec section 16 ("avoid a large ML-specific schema"). No
`recommendations` table is added: `backend.app.domain.recommendation.
Recommendation` (the existing OperationalState-derived type) is never
persisted anywhere in this codebase either — this PR follows that same
convention for its own `FaultRecommendation`. Timeline entries reuse the
existing `TimelineEvent`/`SqlAlchemyTimelineRepository` directly (five new
`TimelineEventType` values added: `ai_fault_alert_received`,
`ai_fault_corroboration_completed`, `ai_fault_investigation_updated`,
`ai_fault_recommendation_recorded`, `ai_fault_alert_cleared` — a
"corroboration started" entry was deliberately *not* added, since this is
a synchronous, sub-second deterministic check with no useful gap for a
"started" milestone to describe).

**Only the small curated `evidence_items` (≤5, from PR176's own
`evidence.build_evidence`) are stored — never all 153 model features.**

## Transaction boundary / outbox strategy

`ReasoningBridgeService.process_alert_transition` is one atomic unit: one
`UnitOfWork`, one commit, covering the evidence row and all of that
alert's timeline entries together. Kafka publication is a **separate**
step *after* that commit — PostgreSQL and Kafka have no shared
transaction, so this is not a distributed transaction, it is an
idempotent at-least-once pipeline: the worker commits its consumer offset
only after both persistence *and* publish succeed
(`ReasoningBridgeWorker._handle_message`). If persistence succeeds but
publish then fails, the offset is not committed, the message is
redelivered, and reprocessing becomes a no-op replay (the evidence row
already exists) that simply re-attempts the publish with the same
deterministic event_id — never a second domain write.

## Topics and event contracts

| Role | Env var | Default |
| --- | --- | --- |
| Input | `REASONING_BRIDGE_INPUT_TOPIC` | `odis.fault.alert-transitions.v1` |
| Output | `REASONING_BRIDGE_OUTPUT_TOPIC` | `odis.fault.reasoning-results.v1` |
| Consumer group | `REASONING_BRIDGE_CONSUMER_GROUP_ID` | `odis-reasoning-bridge` |

Input: PR177's `fault_alert_transition.v1` — extended by this PR with two
small, backward-compatible fields it was missing but this bridge's own
evidence contract requires: `feature_schema_version` and
`class_scores`/`maximum_score` (previously only the curated `evidence`
summary was published). Every other field/consumer of that event is
unaffected.

Output — `fault_reasoning_result.v1`:

```json
{
  "event_id": "...", "event_version": "v1", "occurred_at": "...",
  "source_alert_event_id": "...", "asset_id": "...",
  "diagnosed_class": "cooling_degradation",
  "corroboration_result": "corroborated",
  "investigation_id": "...", "operational_situation_id": null,
  "recommendation_status": "produced",
  "recommendation_action_summary": "...",
  "urgency": "ELEVATED",
  "supporting_rule_ids": ["cooling_degradation.stack_temperature_increasing", "..."],
  "supporting_observation_ids": ["...", "..."],
  "model_system_version": "plant_alpha_fault_v1", "model_hash": "...",
  "reasoning_rule_version": "1.0"
}
```

`operational_situation_id` is always `null` — this bridge never invokes
the 7-stage `ReasoningSession` pipeline, so it never produces an
`OperationalSituation`. Never publishes raw feature arrays, full class
scores, or internal corroboration notes — only the fields above.

## Metrics

`backend/app/infrastructure/metrics/reasoning_bridge_metrics.py`,
registered in the shared `registry.py` and exposed via a dedicated
`start_http_server(REASONING_BRIDGE_METRICS_PORT)` (default `9109`),
scraped by Prometheus as `odis-reasoning-bridge-worker`. No raw `asset_id`
label anywhere. Key metrics: `reasoning_bridge_alert_transitions_consumed_
total`, `reasoning_bridge_malformed_events_total{reason}`,
`reasoning_bridge_duplicate_events_ignored_total`,
`reasoning_bridge_corroboration_results_total{result}`,
`reasoning_bridge_investigations_created_total`,
`reasoning_bridge_investigations_updated_total`,
`reasoning_bridge_recommendations_produced_total`,
`reasoning_bridge_recommendations_withheld_total`,
`reasoning_bridge_class_change_updates_total`,
`reasoning_bridge_clear_transitions_processed_total`,
`reasoning_bridge_failures_total`,
`reasoning_bridge_processing_latency_seconds`,
`reasoning_bridge_publish_failures_total`,
`reasoning_bridge_worker_starts_total`.

## Local Compose startup

```bash
docker compose --profile demo up --build -d kafka fault-inference-worker reasoning-bridge-worker
```

`reasoning-bridge-worker` depends on `api` (`service_healthy` — so
`alembic upgrade head` has already run) and `kafka` (`service_healthy`).

## End-to-end flow

```
Plant Alpha (--transport kafka+http, ONE process)
  → CompositeObservationPublisher fans out each tick's observations:
      ├─→ odis.telemetry.observations.v1 (Kafka)
      │     → fault-inference-worker (PR177)
      │     → odis.fault.inference-results.v1 / odis.fault.alert-transitions.v1
      │     → reasoning-bridge-worker (this PR): validate → corroborate →
      │       investigation lifecycle → persist → publish
      │     → odis.fault.reasoning-results.v1
      └─→ POST /observations (HTTP)
            → ObservationService.create → observations table
            → later read back by ReasoningBridgeService._corroborate
              for the SAME asset/observations the alert above was raised from
```

`--transport kafka+http` (not two separate simulator processes) is
required for this flow to hold: it is what makes "the same asset/
observations" in the diagram above literally true rather than
approximate. See the PR178 smoke-test report for exact commands,
timestamps, and observed corroboration/recommendation output from a real
single-process run.

## Dashboard integration (PR179)

The dashboard reads the persisted `AiFaultEvidence` rows this bridge
writes — not `fault_reasoning_result.v1` directly, since browser delivery
must not depend on live Kafka connectivity. PR179 added a read-model API,
an SSE bridge (this worker now calls `bootstrap_application_runtime` so a
processed alert also reaches the existing outbox → `DomainEventBus` →
Redis pub/sub → SSE pipeline), and dashboard components. See
`docs/fault-investigation-dashboard.md` for the full design. This bridge
itself gained no new UI or FastAPI endpoint of its own — only the SSE
wiring described above and in that doc.
